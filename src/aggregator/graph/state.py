"""
LangGraph state schemas for the news aggregator.

This module defines:
1. RawItem - Collected items from RSS/Gmail before processing
2. ProcessedItem - Items after summarization and enrichment
3. CollectionError - Errors during collection (non-fatal)
4. AggregatorState - The main graph state passed between nodes
"""

import operator
from datetime import datetime
from typing import Annotated, Literal, TypedDict

# Article type classification
ARTICLE_TYPES = ["news", "tutorial"]


class RawItem(TypedDict):
    """
    A news item as collected from RSS or Gmail, before processing.

    This is the "raw" format - minimal transformation from source.
    The summarize node will enrich this into ProcessedItem.
    """

    source_type: Literal["rss", "gmail"]
    source_id: str  # Feed URL or sender email
    item_id: str  # Unique identifier (hash of url+title or message_id)
    title: str | None  # May be missing in some emails
    content: str  # Main text content
    author: str | None
    published_at: datetime
    url: str | None  # None for emails without links
    raw_metadata: dict  # Source-specific data (feed info, email headers, etc.)


class ProcessedItem(TypedDict):
    """
    A news item after LLM processing.

    This is what gets stored in the database and served via API.
    Contains AI-generated summary, key points, and relevance scoring.
    """

    item_id: str
    title: str  # LLM may generate title if missing
    summary: str  # 2-3 paragraph summary
    key_points: list[str]  # 3-5 bullet points
    topics: list[str]  # From predefined topic list
    article_type: str  # "news" or "tutorial"
    relevance_score: float  # 0-1, items < 0.3 are filtered out
    original_urls: list[str]  # May have multiple if deduplicated
    source_types: list[str]  # ["rss"], ["gmail"], or ["rss", "gmail"]
    published_at: datetime
    processed_at: datetime
    embedding: list[float] | None  # 1536-dim OpenAI embedding for similarity


# Predefined topic categories for classification
TOPIC_CATEGORIES = [
    "LLMs",
    "AI Agents",
    "AI Safety",
    "MLOps",
    "Computer Vision",
    "NLP",
    "Open Source",
    "Products",
    "Research",
    "Industry",
]


class CollectionError(TypedDict):
    """
    Non-fatal error during collection.

    We log these but don't fail the pipeline - partial results are better
    than no results. Errors are included in the final publication payload.
    """

    source_type: Literal["rss", "gmail"]
    source_id: str  # Which feed/sender failed
    error_type: str  # Exception class name
    error_message: str  # Human-readable message
    timestamp: datetime


class AggregatorState(TypedDict, total=False):
    """
    Main state for the aggregator graph.

    This state flows through all nodes:
    START -> [RSS, Gmail] -> Deduplicate -> Summarize -> Persist -> Publish -> END

    Key patterns:
    1. `total=False` means all fields are optional (nodes return partial updates)
    2. `Annotated[list, operator.add]` merges parallel node outputs
    3. Input fields (run_id, etc.) are set once at the start
    4. Processing fields are updated as the pipeline progresses

    Example flow:
    - START sets: run_id, run_date, backfill_days
    - RSS/Gmail set: raw_items (merged via operator.add)
    - Deduplicate sets: deduplicated_items
    - Summarize sets: processed_items
    - Persist sets: persisted_count
    - Publish sets: publication_payload
    """

    # === Input (set at pipeline start) ===
    run_id: str  # Unique ID for this pipeline run
    run_date: datetime  # When the pipeline was triggered
    backfill_days: int  # 0 = today only, 14 = initial backfill

    # === Collection (parallel nodes merge via operator.add) ===
    # The Annotated type tells LangGraph to concatenate lists from parallel nodes
    # instead of having one overwrite the other
    raw_items: Annotated[list[RawItem], operator.add]
    collection_errors: Annotated[list[CollectionError], operator.add]

    # === Processing (sequential nodes) ===
    deduplicated_items: list[RawItem]
    processed_items: list[ProcessedItem]

    # === Output ===
    persisted_count: int
    publication_payload: dict  # Final JSON for API response
