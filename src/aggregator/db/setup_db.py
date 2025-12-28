"""
Database schema setup script.

This script:
1. Creates the pgvector extension
2. Creates the news_items table
3. Creates the pipeline_runs table for tracking runs
4. Creates indexes for efficient querying

Run with:
    python -m aggregator.db.setup_db

Or use the reset function for development:
    python -c "import asyncio; from aggregator.db.setup_db import reset_database; asyncio.run(reset_database())"
"""

import asyncio

import structlog

from aggregator.db.connection import close_db_pool, get_db_pool

logger = structlog.get_logger()


# ============================================================
# SQL SCHEMA DEFINITIONS
# ============================================================

# Enable pgvector extension for vector similarity search
# This must be done before creating tables with vector columns
CREATE_EXTENSION_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
"""

# Main table for storing processed news items
# Key design decisions explained in comments
CREATE_NEWS_ITEMS_SQL = """
CREATE TABLE IF NOT EXISTS news_items (
    -- Primary key: The item_id from our generate_item_id() function
    -- Using VARCHAR(64) because it's a 32-char hex hash, but we leave room
    item_id VARCHAR(64) PRIMARY KEY,

    -- Content fields - all from Claude's structured output
    title TEXT NOT NULL,
    summary TEXT NOT NULL,

    -- JSONB is PostgreSQL's binary JSON format - faster than TEXT for queries
    -- We use it for arrays because PostgreSQL arrays are harder to work with
    key_points JSONB NOT NULL,  -- ["point 1", "point 2", ...]
    topics JSONB NOT NULL,       -- ["LLMs", "Research", ...]

    -- Article type classification: "news" or "tutorial"
    article_type VARCHAR(20) NOT NULL DEFAULT 'news',

    -- Source tracking - preserved from merge_duplicate_items()
    original_urls JSONB NOT NULL,   -- All URLs where this appeared
    source_types JSONB NOT NULL,    -- ["rss"] or ["rss", "gmail"]

    -- Timestamps
    published_at TIMESTAMPTZ NOT NULL,  -- Original publication date
    processed_at TIMESTAMPTZ NOT NULL,  -- When Claude processed it
    created_at TIMESTAMPTZ DEFAULT NOW(),   -- When inserted to DB
    updated_at TIMESTAMPTZ DEFAULT NOW(),   -- Last update time

    -- Vector embedding for similarity search
    -- 1536 dimensions matches OpenAI's text-embedding-3-small model
    embedding vector(1536)
);

-- INDEX DESIGN:
-- Each index optimizes specific query patterns

-- For "get latest news" queries: ORDER BY published_at DESC
CREATE INDEX IF NOT EXISTS idx_news_items_published_at
    ON news_items(published_at DESC);

-- For topic filtering: WHERE topics @> '["LLMs"]'
-- GIN (Generalized Inverted Index) is optimal for JSONB containment queries
CREATE INDEX IF NOT EXISTS idx_news_items_topics
    ON news_items USING GIN(topics);

-- For article type filtering: WHERE article_type = 'tutorial'
CREATE INDEX IF NOT EXISTS idx_news_items_article_type
    ON news_items(article_type);

-- For semantic similarity search using cosine distance
-- IVFFlat divides vectors into clusters for faster approximate search
-- lists=100 means 100 clusters - tune based on data size
CREATE INDEX IF NOT EXISTS idx_news_items_embedding
    ON news_items USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
"""

# Track each pipeline run for monitoring/debugging
CREATE_PIPELINE_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    run_date TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Statistics for monitoring
    items_collected INT DEFAULT 0,
    items_processed INT DEFAULT 0,
    items_persisted INT DEFAULT 0,
    collection_errors INT DEFAULT 0,

    -- Status tracking: 'running', 'completed', 'failed'
    status VARCHAR(20) DEFAULT 'running',
    error_message TEXT
);

-- For "show recent runs" queries
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_run_date
    ON pipeline_runs(run_date DESC);
"""

# Automatically update the updated_at timestamp on any row change
# This is a PostgreSQL trigger - fires BEFORE UPDATE
CREATE_UPDATED_AT_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_news_items_updated_at ON news_items;
CREATE TRIGGER update_news_items_updated_at
    BEFORE UPDATE ON news_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
"""


# ============================================================
# SETUP FUNCTIONS
# ============================================================


async def setup_database() -> None:
    """
    Set up the database schema.

    Creates all tables and indexes if they don't exist.
    Safe to run multiple times (uses IF NOT EXISTS).
    """
    logger.info("Setting up database schema")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        # Step 1: Enable pgvector extension
        logger.info("Creating pgvector extension")
        await conn.execute(CREATE_EXTENSION_SQL)

        # Step 2: Create main news_items table with indexes
        logger.info("Creating news_items table")
        await conn.execute(CREATE_NEWS_ITEMS_SQL)

        # Step 3: Create pipeline_runs table for monitoring
        logger.info("Creating pipeline_runs table")
        await conn.execute(CREATE_PIPELINE_RUNS_SQL)

        # Step 4: Create updated_at trigger
        logger.info("Creating updated_at trigger")
        await conn.execute(CREATE_UPDATED_AT_TRIGGER_SQL)

    logger.info("Database schema setup complete")


async def reset_database() -> None:
    """
    Reset the database by dropping and recreating all tables.

    WARNING: This destroys all data! Only use in development.
    """
    logger.warning("Resetting database - all data will be lost!")

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        # Drop everything (CASCADE handles dependencies)
        await conn.execute("DROP TABLE IF EXISTS news_items CASCADE")
        await conn.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE")
        await conn.execute("DROP FUNCTION IF EXISTS update_updated_at_column CASCADE")

    # Recreate from scratch
    await setup_database()
    logger.info("Database reset complete")


async def get_table_stats() -> dict:
    """
    Get basic statistics about the database.

    Returns:
        Dict with table row counts
    """
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        news_count = await conn.fetchval("SELECT COUNT(*) FROM news_items")
        runs_count = await conn.fetchval("SELECT COUNT(*) FROM pipeline_runs")

    return {
        "news_items": news_count,
        "pipeline_runs": runs_count,
    }


async def main() -> None:
    """Main entry point for running schema setup."""
    try:
        await setup_database()
        stats = await get_table_stats()
        logger.info("Database ready", **stats)
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
