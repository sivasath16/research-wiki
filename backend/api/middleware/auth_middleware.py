import secrets as _secrets
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import redis as redis_lib
from db.session import get_db
from db.models import User
from core.config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key)
_redis: redis_lib.Redis | None = None

SESSION_TTL = 86400 * 30  # 30 days


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


def create_session_token(user_id: int) -> str:
    session_id = _secrets.token_hex(32)
    _get_redis().setex(f"session:{session_id}", SESSION_TTL, str(user_id))
    return _serializer.dumps({"user_id": user_id, "sid": session_id}, salt="session")


def decode_session_token(token: str, max_age: int = SESSION_TTL) -> int:
    try:
        data = _serializer.loads(token, salt="session", max_age=max_age)
        session_id = data.get("sid")
        if session_id and not _get_redis().exists(f"session:{session_id}"):
            raise HTTPException(status_code=401, detail="Session revoked")
        return data["user_id"]
    except HTTPException:
        raise
    except (BadSignature, SignatureExpired, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired session")


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
