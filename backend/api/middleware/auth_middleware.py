from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from db.session import get_db
from db.models import User
from core.config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key)


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"user_id": user_id}, salt="session")


def decode_session_token(token: str, max_age: int = 86400 * 30) -> int:
    try:
        data = _serializer.loads(token, salt="session", max_age=max_age)
        return data["user_id"]
    except (BadSignature, SignatureExpired, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired session")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_session_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        user_id = decode_session_token(token)
        return db.query(User).filter(User.id == user_id).first()
    except HTTPException:
        return None
