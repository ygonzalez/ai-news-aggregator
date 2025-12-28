"""
Persist Node - Saves processed items to PostgreSQL.

This node:
1. Takes processed items from the summarize node
2. Upserts them to the news_items table
3. Tracks the pipeline run in pipeline_runs table

"Upsert" = INSERT if new, UPDATE if exists (ON CONFLICT clause)

Why Upsert?
- If we run the pipeline twice on the same day, we might re-process the same articles
- Upsert ensures we don't get duplicate key errors
- It also updates existing records with the latest processing

LangGraph Integration:
- Input: AggregatorState with processed_items, run_id, run_date
- Output: {"persisted_count": int}
"""

import json
from datetime import UTC, datetime

import structlog

from aggregator.db.connection import get_db_pool
from aggregator.graph.state import AggregatorState, ProcessedItem

logger = structlog.get_logger()


# SQL for upserting a single news item
# ON CONFLICT (item_id) DO UPDATE means:
# - If item_id doesn't exist: INSERT
# - If item_id exists: UPDATE with new values
UPSERT_NEWS_ITEM_SQL = """
INSERT INTO news_items (
    item_id, title, summary, key_points, topics, article_type,
    relevance_score, original_urls, source_types,
    published_at, processed_at, embedding
) VALUES (
    $1, $2, $3, $4, $5, $6,
    $7, $8, $9,
    $10, $11, $12
)
ON CONFLICT (item_id) DO UPDATE SET
    title = EXCLUDED.title,
    summary = EXCLUDED.summary,
    key_points = EXCLUDED.key_points,
    topics = EXCLUDED.topics,
    article_type = EXCLUDED.article_type,
    relevance_score = EXCLUDED.relevance_score,
    original_urls = EXCLUDED.original_urls,
    source_types = EXCLUDED.source_types,
    processed_at = EXCLUDED.processed_at,
    embedding = EXCLUDED.embedding
    -- Note: We preserve the original published_at and created_at
    -- updated_at is handled by the trigger
RETURNING item_id;
"""

# SQL for creating/updating pipeline run record
CREATE_PIPELINE_RUN_SQL = """
INSERT INTO pipeline_runs (run_id, run_date, status)
VALUES ($1, $2, 'running')
ON CONFLICT (run_id) DO UPDATE SET
    status = 'running',
    started_at = NOW();
"""

UPDATE_PIPELINE_RUN_SQL = """
UPDATE pipeline_runs SET
    completed_at = NOW(),
    items_persisted = $2,
    status = $3
WHERE run_id = $1;
"""


async def persist_single_item(
    conn,  # asyncpg connection
    item: ProcessedItem,
) -> bool:
    """
    Persist a single processed item to the database.

    Args:
        conn: Database connection (from pool.acquire())
        item: ProcessedItem to persist

    Returns:
        True if persisted successfully, False otherwise
    """
    try:
        # Convert Python lists to JSON strings for JSONB columns
        key_points_json = json.dumps(item["key_points"])
        topics_json = json.dumps(item["topics"])
        original_urls_json = json.dumps(item["original_urls"])
        source_types_json = json.dumps(item["source_types"])

        # Execute upsert
        result = await conn.fetchval(
            UPSERT_NEWS_ITEM_SQL,
            item["item_id"],
            item["title"],
            item["summary"],
            key_points_json,
            topics_json,
            item["article_type"],
            item["relevance_score"],
            original_urls_json,
            source_types_json,
            item["published_at"],
            item["processed_at"],
            item["embedding"],  # Can be None if embeddings disabled
        )

        return result is not None

    except Exception as e:
        logger.error(
            "Failed to persist item",
            item_id=item["item_id"],
            error=str(e),
            error_type=type(e).__name__,
        )
        return False


async def persist(state: AggregatorState) -> dict:
    """
    LangGraph node: Persist processed items to the database.

    This node:
    1. Creates/updates the pipeline run record
    2. Upserts each processed item
    3. Updates the run record with final counts

    Args:
        state: Current graph state with processed_items

    Returns:
        Partial state update with persisted_count
    """
    items = state.get("processed_items", [])
    run_id = state.get("run_id", "unknown")
    run_date = state.get("run_date", datetime.now(UTC))

    logger.info("Starting persistence", item_count=len(items), run_id=run_id)

    if not items:
        logger.warning("No items to persist")
        return {"persisted_count": 0}

    pool = await get_db_pool()
    persisted_count = 0

    async with pool.acquire() as conn:
        # Start a transaction for atomicity
        async with conn.transaction():
            # Record pipeline run start
            await conn.execute(CREATE_PIPELINE_RUN_SQL, run_id, run_date)

            # Persist each item
            for item in items:
                if await persist_single_item(conn, item):
                    persisted_count += 1

            # Update pipeline run with results
            await conn.execute(
                UPDATE_PIPELINE_RUN_SQL,
                run_id,
                persisted_count,
                "completed",
            )

    logger.info(
        "Persistence complete",
        persisted_count=persisted_count,
        total_items=len(items),
        run_id=run_id,
    )

    return {"persisted_count": persisted_count}


async def get_recent_items(
    limit: int = 20,
    topic: str | None = None,
    article_type: str | None = None,
    min_relevance: float = 0.0,
) -> list[dict]:
    """
    Query recent news items from the database.

    This is a utility function for the API layer.

    Args:
        limit: Maximum number of items to return
        topic: Optional topic filter (e.g., "LLMs")
        article_type: Optional article type filter ("news" or "tutorial")
        min_relevance: Minimum relevance score

    Returns:
        List of news items as dicts
    """
    pool = await get_db_pool()

    # Build query dynamically based on filters
    query = """
        SELECT
            item_id, title, summary, key_points, topics, article_type,
            relevance_score, original_urls, source_types,
            published_at, processed_at
        FROM news_items
        WHERE relevance_score >= $1
    """
    params: list = [min_relevance]

    if topic:
        # JSONB containment operator: topics @> '["LLMs"]'
        query += f" AND topics @> ${len(params) + 1}::jsonb"
        params.append(json.dumps([topic]))

    if article_type:
        query += f" AND article_type = ${len(params) + 1}"
        params.append(article_type)

    query += f" ORDER BY published_at DESC LIMIT ${len(params) + 1}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    # Convert rows to dicts and parse JSONB fields
    items = []
    for row in rows:
        item = dict(row)
        # Parse JSONB fields back to Python lists
        item["key_points"] = json.loads(item["key_points"])
        item["topics"] = json.loads(item["topics"])
        item["original_urls"] = json.loads(item["original_urls"])
        item["source_types"] = json.loads(item["source_types"])
        items.append(item)

    return items
