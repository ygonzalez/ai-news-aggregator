"""
Database connection management using asyncpg.

This module provides:
1. Connection pool management (singleton pattern)
2. Context managers for transactions
3. Health check utilities

Usage:
    from aggregator.db import get_db_pool

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetch("SELECT * FROM news_items")

    # At shutdown:
    await close_db_pool()

Connection Pool:
- Uses asyncpg.create_pool() for efficient connection reuse
- Pool is created lazily on first use
- Single pool is shared across the application
"""

import asyncpg
import structlog

from aggregator.config import get_settings

logger = structlog.get_logger()

# Global connection pool (singleton)
_pool: asyncpg.Pool | None = None


async def get_db_pool() -> asyncpg.Pool:
    """
    Get or create the database connection pool.

    The pool is created lazily on first call and reused thereafter.
    This function is safe to call multiple times.

    Returns:
        asyncpg.Pool: Connection pool

    Raises:
        asyncpg.PostgresError: If connection fails
    """
    global _pool

    if _pool is None:
        settings = get_settings()
        logger.info(
            "Creating database connection pool", database_url=settings.database_url[:50] + "..."
        )

        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=2,  # Minimum connections to keep open
            max_size=10,  # Maximum connections
            command_timeout=60,
            # Register custom type codecs for pgvector
            init=_init_connection,
        )

        logger.info("Database pool created", min_size=2, max_size=10)

    return _pool


async def _init_connection(conn: asyncpg.Connection) -> None:
    """
    Initialize each connection with custom type codecs.

    This is called for each new connection in the pool.
    We use it to register the vector type for pgvector.
    """
    # Register vector type for pgvector
    # The vector type is stored as text in wire format
    # Note: This may fail if pgvector extension isn't installed yet (e.g., during setup)
    try:
        await conn.set_type_codec(
            "vector",
            encoder=_encode_vector,
            decoder=_decode_vector,
            schema="public",
            format="text",
        )
    except Exception:
        # Extension not yet installed - this is fine during initial setup
        pass


def _encode_vector(vector: list[float]) -> str:
    """Encode a Python list to PostgreSQL vector format."""
    return "[" + ",".join(str(v) for v in vector) + "]"


def _decode_vector(data: str) -> list[float]:
    """Decode PostgreSQL vector format to Python list."""
    # Format: [0.1,0.2,0.3,...]
    return [float(v) for v in data[1:-1].split(",")]


async def close_db_pool() -> None:
    """
    Close the database connection pool.

    Should be called during application shutdown.
    Safe to call even if pool was never created.
    """
    global _pool

    if _pool is not None:
        logger.info("Closing database pool")
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def check_db_health() -> bool:
    """
    Check if the database is reachable.

    Returns:
        True if healthy, False otherwise
    """
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return False


async def check_pgvector_extension() -> bool:
    """
    Check if pgvector extension is installed.

    Returns:
        True if pgvector is available, False otherwise
    """
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            )
        return result
    except Exception as e:
        logger.error("pgvector check failed", error=str(e))
        return False
