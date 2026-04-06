import secrets
import httpx
import redis as redis_lib
from typing import Annotated

from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from db.session import get_db
from db.rls_context import oauth_rls_dependency
from db.models import User
from core.config import settings
from core.security import encrypt_token
from api.middleware.auth_middleware import create_session_token, get_current_user, revoke_session_token

router = APIRouter()

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

_redis: redis_lib.Redis | None = None


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


@router.get("/login")
async def login():
    """Redirect browser to GitHub OAuth consent page."""
    state = secrets.token_urlsafe(32)
    _get_redis().setex(f"oauth_state:{state}", 300, "1")  # 5 min TTL

    params = (
        f"client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_callback_url}"
        f"&scope=repo,read:user,user:email"
        f"&state={state}"
    )
    return RedirectResponse(url=f"{GITHUB_AUTH_URL}?{params}")


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    request: Request,
    _: Annotated[None, Depends(oauth_rls_dependency)],
    db: Session = Depends(get_db),
):
    """Exchange OAuth code for access token, upsert user, set session cookie."""
    # Validate OAuth state to prevent CSRF
    r = _get_redis()
    state_key = f"oauth_state:{state}"
    if not r.get(state_key):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    r.delete(state_key)

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_callback_url,
            },
        )
        token_data = token_resp.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="GitHub OAuth failed: no access token")

    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        gh_user = user_resp.json()

    github_id = gh_user["id"]
    # oauth_rls_dependency + get_db: after_begin applies app.service_mode for this transaction.
    user = db.query(User).filter(User.github_id == github_id).first()

    if user:
        user.login = gh_user["login"]
        user.name = gh_user.get("name")
        user.email = gh_user.get("email")
        user.avatar_url = gh_user.get("avatar_url")
        user.github_token_encrypted = encrypt_token(access_token)
        user.updated_at = datetime.utcnow()
    else:
        user = User(
            github_id=github_id,
            login=gh_user["login"],
            name=gh_user.get("name"),
            email=gh_user.get("email"),
            avatar_url=gh_user.get("avatar_url"),
            github_token_encrypted=encrypt_token(access_token),
        )
        db.add(user)

    db.commit()
    db.refresh(user)

    session_token = create_session_token(user.id)
    response = RedirectResponse(url=f"{settings.frontend_url}/")
    response.set_cookie(
        key="session",
        value=session_token,
        httponly=True,
        samesite="strict",
        max_age=86400 * 30,
        secure=settings.cookie_secure,
    )
    return response


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "github_id": current_user.github_id,
        "login": current_user.login,
        "name": current_user.name,
        "email": current_user.email,
        "avatar_url": current_user.avatar_url,
        "created_at": current_user.created_at,
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session")
    if token:
        revoke_session_token(token)
    response.delete_cookie("session")
    return {"status": "logged out"}
