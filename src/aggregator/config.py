"""
Configuration management using pydantic-settings.

Environment variables are loaded from:
1. .env file (if present)
2. System environment variables (override .env)

Usage:
    from aggregator.config import get_settings
    settings = get_settings()
    print(settings.database_url)
"""

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# === Data Source Configuration ===
# These are Pydantic models (not settings) - they define the structure
# of RSS feeds and Gmail senders. Defaults are provided below.


class RssFeedConfig(BaseModel):
    """Configuration for a single RSS feed."""

    name: str
    url: str


class GmailSenderConfig(BaseModel):
    """Configuration for a Gmail newsletter sender."""

    name: str
    email: str


# Default RSS feeds (from design doc)
DEFAULT_RSS_FEEDS: list[RssFeedConfig] = [
    RssFeedConfig(name="LangChain Blog", url="https://blog.langchain.dev/rss/"),
    RssFeedConfig(name="OpenAI Blog", url="https://openai.com/blog/rss.xml"),
    RssFeedConfig(name="Google AI Blog", url="https://blog.google/technology/ai/rss/"),
    RssFeedConfig(name="Lenny's Newsletter", url="https://www.lennysnewsletter.com/feed"),
    RssFeedConfig(name="Hugo Bowne-Anderson", url="https://hugobowne.substack.com/feed"),
    RssFeedConfig(name="Decoding AI", url="https://www.decodingai.com/feed"),
    RssFeedConfig(name="Ben's Bites", url="https://www.bensbites.com/feed"),
    RssFeedConfig(name="One Useful Thing", url="https://www.oneusefulthing.org/feed"),
    # # Medium tags
    # RssFeedConfig(name="Medium - AI", url="https://medium.com/feed/tag/ai"),
    # RssFeedConfig(name="Medium - Data Extraction", url="https://medium.com/feed/tag/data-extraction"),
    # RssFeedConfig(name="Medium - Agentic AI", url="https://medium.com/feed/tag/agentic-ai"),
    # RssFeedConfig(name="Medium - LangChain", url="https://medium.com/feed/tag/langchain"),
    # RssFeedConfig(name="Medium - LangGraph", url="https://medium.com/feed/tag/langgraph"),
    # RssFeedConfig(name="Medium - LLM", url="https://medium.com/feed/tag/llm"),
]

# Default Gmail senders (from design doc)
DEFAULT_GMAIL_SENDERS: list[GmailSenderConfig] = [
    GmailSenderConfig(name="TLDR AI", email="dan@tldrnewsletter.com"),
    GmailSenderConfig(name="The Batch", email="thebatch@deeplearning.ai"),
]


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
        default="postgresql://postgres:postgres@localhost:5433/news_aggregator",
        description="PostgreSQL connection string (port 5433 to avoid local PostgreSQL conflict)",
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
        return all(
            [
                self.gmail_client_id,
                self.gmail_client_secret,
                self.gmail_refresh_token,
            ]
        )


# Singleton instance - import this in other modules
# Note: This will raise ValidationError on import if required vars are missing
# For testing, you can create Settings() with explicit values
def get_settings() -> Settings:
    """Get settings instance. Use this for lazy loading in tests."""
    return Settings()
