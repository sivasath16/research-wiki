"""
Signed session cookie parsing (itsdangerous + Redis). Used by RLS context and auth middleware.
"""
import redis as redis_lib
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from core.config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key)
_redis: redis_lib.Redis | None = None

SESSION_TTL = 86400 * 30  # 30 days


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


def try_session_user_id(token: str | None, max_age: int = SESSION_TTL) -> int | None:
    """
    Return user_id from session cookie, or None if missing / invalid / revoked.
    Does not raise — used to set PostgreSQL RLS GUC before ORM queries.
    """
    if not token:
        return None
    try:
        data = _serializer.loads(token, salt="session", max_age=max_age)
        session_id = data.get("sid")
        if session_id and not _get_redis().exists(f"session:{session_id}"):
            return None
        return data["user_id"]
    except (BadSignature, SignatureExpired, KeyError):
        return None
