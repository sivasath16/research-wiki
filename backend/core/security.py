from cryptography.fernet import Fernet
from core.config import settings


def _get_fernet() -> Fernet:
    key = settings.fernet_key
    if not key:
        # Generate a dev key if not configured — not safe for production
        key = Fernet.generate_key().decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(token: str) -> str:
    f = _get_fernet()
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()
