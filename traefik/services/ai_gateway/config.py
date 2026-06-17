"""Central settings — all values come from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Service
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    api_secret: str = ""  # shared secret for Odoo→gateway calls (Bearer token)

    # Postgres (pgvector)
    database_url: str = "postgresql://odoo:odoo@db:5432/odoo"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # AI providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    ollama_base_url: str = "http://host.docker.internal:11434"

    # Default provider + model
    default_provider: str = "mock"  # mock | anthropic | openai | ollama | azure
    default_model: str = ""
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # RAG
    chunk_size: int = 512
    chunk_overlap: int = 64
    rag_top_k: int = 5
    rag_min_score: float = 0.30

    # Redaction
    redact_pii_external: bool = True  # strip PII before external provider calls


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
