"""
Configuration management using pydantic-settings.

Environment variables are loaded from:
1. .env file (if present)
2. System environment variables (override .env)

Usage:
    from aggregator.config import settings
    print(settings.database_url)
"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # DATABASE_URL == database_url
        extra="ignore",  # Ignore unknown env vars
    )

    # Database
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/news_aggregator",
        description="PostgreSQL connection string",
    )

    # LLM - Anthropic (for summarization)
    anthropic_api_key: SecretStr = Field(
        default=...,  # Required - no default
        description="Anthropic API key for Claude",
    )

    # LLM - OpenAI (for embeddings only)
    openai_api_key: SecretStr = Field(
        default=...,  # Required - no default
        description="OpenAI API key for embeddings",
    )

    # LangSmith (optional - tracing is auto-enabled when set)
    langsmith_tracing: bool = Field(
        default=False,
        description="Enable LangSmith tracing",
    )
    langsmith_api_key: SecretStr | None = Field(
        default=None,
        description="LangSmith API key",
    )
    langsmith_project: str = Field(
        default="ai-news-aggregator",
        description="LangSmith project name",
    )

    # Gmail OAuth (optional - collector is skipped if not set)
    gmail_client_id: str | None = Field(
        default=None,
        description="Gmail OAuth client ID",
    )
    gmail_client_secret: SecretStr | None = Field(
        default=None,
        description="Gmail OAuth client secret",
    )
    gmail_refresh_token: SecretStr | None = Field(
        default=None,
        description="Gmail OAuth refresh token",
    )

    # Application settings
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    @property
    def gmail_configured(self) -> bool:
        """Check if Gmail credentials are fully configured."""
        return all([
            self.gmail_client_id,
            self.gmail_client_secret,
            self.gmail_refresh_token,
        ])


# Singleton instance - import this in other modules
# Note: This will raise ValidationError on import if required vars are missing
# For testing, you can create Settings() with explicit values
def get_settings() -> Settings:
    """Get settings instance. Use this for lazy loading in tests."""
    return Settings()