from pydantic import Field, model_validator
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "postgresql://rwuser:rwpass@localhost:5432/researchwiki"
    redis_url: str = "redis://localhost:6379"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672//"

    github_client_id: str = ""
    github_client_secret: str = ""
    github_callback_url: str = "http://localhost/api/auth/callback"

    anthropic_api_key: str = ""

    fernet_key: str = ""
    secret_key: str = "change-me-in-production"

    frontend_url: str = "http://localhost"
    # Explicit CORS allowlist — defaults to frontend_url only if not set
    cors_origins: list[str] = Field(default_factory=list)

    # Cookie security — set True in production (requires HTTPS)
    cookie_secure: bool = False

    # Model names
    haiku_model: str = "claude-haiku-4-5"
    sonnet_model: str = "claude-sonnet-4-5"
    embedding_model: str = "jinaai/jina-embeddings-v2-base-code"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Rate limiting
    daily_query_limit: int = 20

    # Ingestion
    max_file_size_bytes: int = 500 * 1024  # 500KB
    max_file_lines: int = 10000
    chunk_max_tokens: int = 512
    chunk_min_tokens: int = 50
    embed_batch_size: int = 64
    max_repo_size_kb: int = 500_000  # 500MB

    # Max concurrent ingestion jobs per user
    max_concurrent_jobs: int = 3

    @model_validator(mode="after")
    def validate_secrets(self):
        if self.secret_key == "change-me-in-production":
            raise ValueError(
                "SECRET_KEY must be set to a random secret. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if not self.fernet_key:
            raise ValueError(
                "FERNET_KEY must be set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set.")
        if not self.github_client_id or not self.github_client_secret:
            raise ValueError("GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be set.")
        if not self.cors_origins:
            self.cors_origins = [self.frontend_url]
        return self

    class Config:
        env_file = "../.env"
        extra = "ignore"


settings = Settings()
