"""
FastAPI application for the news aggregator.

This module provides:
1. REST API endpoints for querying news
2. Trigger endpoint for running the pipeline
3. Health check endpoints

Endpoints:
- GET /: Health check and API info
- GET /health: Detailed health status
- POST /run: Trigger pipeline run
- GET /items: Get recent news items
- GET /items/{item_id}: Get specific item
- GET /topics: Get available topics

Usage:
    # Run with uvicorn
    uvicorn aggregator.api:app --reload

    # Or use the main.py entrypoint
    python -m aggregator.main
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aggregator.db import close_db_pool, get_db_pool
from aggregator.db.connection import check_db_health, check_pgvector_extension
from aggregator.graph import ARTICLE_TYPES, TOPIC_CATEGORIES, run_aggregator
from aggregator.graph.nodes.persist import get_recent_items

logger = structlog.get_logger()


# ========================================
# LIFESPAN MANAGEMENT
# Setup and teardown for the application
# ========================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    This runs:
    - Before startup: Initialize database pool
    - After shutdown: Close database pool

    FastAPI 0.93+ uses lifespan instead of on_event decorators.
    """
    # Startup
    logger.info("Starting API server")
    try:
        await get_db_pool()
        logger.info("Database pool initialized")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        # Continue anyway - health check will report the issue

    yield

    # Shutdown
    logger.info("Shutting down API server")
    await close_db_pool()


# ========================================
# FASTAPI APP
# ========================================

app = FastAPI(
    title="AI News Aggregator",
    description="Aggregates and summarizes AI/ML news from RSS feeds and newsletters",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ========================================
# PYDANTIC MODELS
# Request/response schemas with validation
# ========================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(description="Overall health status: healthy or unhealthy")
    database: bool = Field(description="Database connection status")
    pgvector: bool = Field(description="pgvector extension status")
    timestamp: datetime = Field(description="Current server time")


class RunRequest(BaseModel):
    """Request to trigger a pipeline run."""

    backfill_days: int = Field(
        default=0,
        ge=0,
        le=30,
        description="Days of historical data to collect (0-30)",
    )


class RunResponse(BaseModel):
    """Response after triggering a pipeline run."""

    status: str = Field(description="Run status: started, completed, or failed")
    run_id: str | None = Field(description="Unique run identifier")
    message: str = Field(description="Human-readable status message")
    stats: dict | None = Field(default=None, description="Run statistics if completed")


class NewsItem(BaseModel):
    """A processed news item."""

    id: str = Field(description="Unique item identifier")
    title: str = Field(description="Article title")
    summary: str = Field(description="AI-generated summary")
    key_points: list[str] = Field(description="Key takeaways")
    topics: list[str] = Field(description="Topic categories")
    article_type: str = Field(description="Article type (news or tutorial)")
    relevance_score: float = Field(description="Relevance to AI/ML (0-1)")
    urls: list[str] = Field(description="Original source URLs")
    sources: list[str] = Field(description="Source types (rss, gmail)")
    published_at: datetime = Field(description="Original publication date")


class ItemsResponse(BaseModel):
    """Response containing news items."""

    items: list[NewsItem] = Field(description="List of news items")
    count: int = Field(description="Number of items returned")
    total: int | None = Field(default=None, description="Total matching items")


class TopicsResponse(BaseModel):
    """Response containing available topics."""

    topics: list[str] = Field(description="Available topic categories")


class ArticleTypesResponse(BaseModel):
    """Response containing available article types."""

    article_types: list[str] = Field(description="Available article types")


# ========================================
# ENDPOINTS
# ========================================


@app.get("/", tags=["Health"])
async def root():
    """
    Root endpoint - basic API info.

    Returns a simple greeting and API version.
    """
    return {
        "name": "AI News Aggregator API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Detailed health check.

    Checks:
    - Database connectivity
    - pgvector extension availability

    Returns unhealthy if any component is down.
    """
    db_healthy = await check_db_health()
    pgvector_available = await check_pgvector_extension() if db_healthy else False

    status = "healthy" if (db_healthy and pgvector_available) else "unhealthy"

    return HealthResponse(
        status=status,
        database=db_healthy,
        pgvector=pgvector_available,
        timestamp=datetime.now(UTC),
    )


@app.post("/run", response_model=RunResponse, tags=["Pipeline"])
async def trigger_run(
    request: RunRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger a pipeline run.

    The pipeline runs in the background and collects news from all sources.

    Args:
        request: Run configuration (backfill_days)
        background_tasks: FastAPI background task manager

    Returns:
        Run status and ID for tracking
    """
    run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

    logger.info(
        "Pipeline run triggered via API", run_id=run_id, backfill_days=request.backfill_days
    )

    try:
        # Run synchronously for now (small scale)
        # For production, use background_tasks or a queue
        result = await run_aggregator(backfill_days=request.backfill_days)

        return RunResponse(
            status="completed",
            run_id=result.get("meta", {}).get("run_id", run_id),
            message=f"Pipeline completed. Processed {result.get('stats', {}).get('total_items', 0)} items.",
            stats=result.get("stats"),
        )

    except Exception as e:
        logger.error("Pipeline run failed", error=str(e), run_id=run_id)
        return RunResponse(
            status="failed",
            run_id=run_id,
            message=f"Pipeline failed: {str(e)}",
            stats=None,
        )


@app.get("/items", response_model=ItemsResponse, tags=["News"])
async def get_items(
    limit: Annotated[int, Query(ge=1, le=100, description="Max items to return")] = 20,
    topic: Annotated[str | None, Query(description="Filter by topic")] = None,
    article_type: Annotated[str | None, Query(description="Filter by article type (news or tutorial)")] = None,
    min_relevance: Annotated[float, Query(ge=0, le=1, description="Minimum relevance score")] = 0.0,
):
    """
    Get recent news items.

    Supports filtering by topic, article type, and minimum relevance score.
    Items are sorted by publication date (newest first).

    Args:
        limit: Maximum number of items to return (1-100)
        topic: Optional topic filter (e.g., "LLMs", "AI Safety")
        article_type: Optional article type filter ("news" or "tutorial")
        min_relevance: Minimum relevance score (0-1)

    Returns:
        List of news items matching the filters
    """
    try:
        items = await get_recent_items(
            limit=limit,
            topic=topic,
            article_type=article_type,
            min_relevance=min_relevance,
        )

        # Convert to response format
        news_items = [
            NewsItem(
                id=item["item_id"],
                title=item["title"],
                summary=item["summary"],
                key_points=item["key_points"],
                topics=item["topics"],
                article_type=item.get("article_type", "news"),
                relevance_score=item["relevance_score"],
                urls=item["original_urls"],
                sources=item["source_types"],
                published_at=item["published_at"],
            )
            for item in items
        ]

        return ItemsResponse(
            items=news_items,
            count=len(news_items),
        )

    except Exception as e:
        logger.error("Failed to fetch items", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch items")


@app.get("/items/{item_id}", response_model=NewsItem, tags=["News"])
async def get_item(item_id: str):
    """
    Get a specific news item by ID.

    Args:
        item_id: The unique item identifier

    Returns:
        The news item if found

    Raises:
        404: If item not found
    """
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT item_id, title, summary, key_points, topics, article_type,
                       relevance_score, original_urls, source_types, published_at
                FROM news_items
                WHERE item_id = $1
                """,
                item_id,
            )

        if row is None:
            raise HTTPException(status_code=404, detail="Item not found")

        import json

        return NewsItem(
            id=row["item_id"],
            title=row["title"],
            summary=row["summary"],
            key_points=json.loads(row["key_points"]),
            topics=json.loads(row["topics"]),
            article_type=row.get("article_type", "news"),
            relevance_score=row["relevance_score"],
            urls=json.loads(row["original_urls"]),
            sources=json.loads(row["source_types"]),
            published_at=row["published_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch item", item_id=item_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch item")


@app.get("/topics", response_model=TopicsResponse, tags=["News"])
async def get_topics():
    """
    Get available topic categories.

    These are the predefined categories used for classification.

    Returns:
        List of topic category names
    """
    return TopicsResponse(topics=TOPIC_CATEGORIES)


@app.get("/article-types", response_model=ArticleTypesResponse, tags=["News"])
async def get_article_types():
    """
    Get available article types.

    Returns:
        List of article types (news, tutorial)
    """
    return ArticleTypesResponse(article_types=ARTICLE_TYPES)
