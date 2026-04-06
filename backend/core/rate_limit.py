import redis as redis_lib
from datetime import date
from core.config import settings

_redis: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _key(user_id: int) -> str:
    return f"ratelimit:{user_id}:{date.today().isoformat()}"


def get_remaining(user_id: int) -> int:
    r = get_redis()
    val = r.get(_key(user_id))
    used = int(val) if val else 0
    return max(0, settings.daily_query_limit - used)


def consume(user_id: int) -> tuple[bool, int]:
    """Returns (allowed, remaining). Increments counter atomically."""
    r = get_redis()
    k = _key(user_id)
    pipe = r.pipeline()
    pipe.incr(k)
    pipe.expire(k, 86400)  # 24h TTL
    results = pipe.execute()
    used = results[0]
    remaining = max(0, settings.daily_query_limit - used)
    allowed = used <= settings.daily_query_limit
    return allowed, remaining
