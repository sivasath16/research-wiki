import secrets as _secrets
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from db.session import get_db
from db.models import User
from core.session_cookie import (
    SESSION_TTL,
    _get_redis,
    _serializer,
    try_session_user_id,
)


def create_session_token(user_id: int) -> str:
    session_id = _secrets.token_hex(32)
    _get_redis().setex(f"session:{session_id}", SESSION_TTL, str(user_id))
    return _serializer.dumps({"user_id": user_id, "sid": session_id}, salt="session")


def decode_session_token(token: str, max_age: int = SESSION_TTL) -> int:
    uid = try_session_user_id(token, max_age=max_age)
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return uid


def revoke_session_token(token: str) -> None:
    """Delete the server-side session entry so the token becomes immediately invalid."""
    try:
        data = _serializer.loads(token, salt="session", max_age=SESSION_TTL)
        session_id = data.get("sid")
        if session_id:
            _get_redis().delete(f"session:{session_id}")
    except Exception:
        pass


def get_current_user(conn: HTTPConnection, db: Session = Depends(get_db)) -> User:
    token = conn.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_session_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_optional_user(conn: HTTPConnection, db: Session = Depends(get_db)) -> User | None:
    token = conn.cookies.get("session")
    if not token:
        return None
    try:
        user_id = decode_session_token(token)
        return db.query(User).filter(User.id == user_id).first()
    except HTTPException:
        return None
