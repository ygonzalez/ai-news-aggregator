"""
Publish Node - Formats the final output payload.

This node:
1. Takes all processed data from the pipeline
2. Formats it into a structured JSON payload
3. Groups items by topic for easy consumption
4. Includes metadata about the run

This is the final node before END in the LangGraph.
The publication_payload can be:
- Returned via API
- Sent to a webhook
- Published to a message queue
- Saved to a file

LangGraph Integration:
- Input: AggregatorState with processed_items, persisted_count, etc.
- Output: {"publication_payload": {...}}
"""

from datetime import UTC, datetime
from typing import Any

import structlog

from aggregator.graph.state import AggregatorState, ProcessedItem

logger = structlog.get_logger()


def format_item_for_api(item: ProcessedItem) -> dict:
    """
    Format a ProcessedItem for the API response.

    Converts datetime objects to ISO strings and removes internal fields.
    """
    return {
        "id": item["item_id"],
        "title": item["title"],
        "summary": item["summary"],
        "key_points": item["key_points"],
        "topics": item["topics"],
        "relevance_score": item["relevance_score"],
        "urls": item["original_urls"],
        "sources": item["source_types"],
        "published_at": item["published_at"].isoformat(),
        "processed_at": item["processed_at"].isoformat(),
        # Omit embedding - too large for API response
    }


def group_items_by_topic(items: list[ProcessedItem]) -> dict[str, list[dict]]:
    """
    Group items by their primary topic.

    Each item can have multiple topics, but we use the first one
    as the primary for grouping purposes.

    Returns:
        Dict mapping topic names to lists of items
    """
    grouped: dict[str, list[dict]] = {}

    for item in items:
        formatted = format_item_for_api(item)
        topics = item.get("topics", [])

        # Use first topic as primary, or "Uncategorized"
        primary_topic = topics[0] if topics else "Uncategorized"

        if primary_topic not in grouped:
            grouped[primary_topic] = []
        grouped[primary_topic].append(formatted)

    # Sort each group by relevance
    for topic in grouped:
        grouped[topic].sort(key=lambda x: x["relevance_score"], reverse=True)

    return grouped


def generate_summary_stats(
    state: AggregatorState,
    items: list[ProcessedItem],
) -> dict[str, Any]:
    """
    Generate summary statistics for the pipeline run.

    Returns:
        Dict with various stats about the run
    """
    # Topic distribution
    topic_counts: dict[str, int] = {}
    for item in items:
        for topic in item.get("topics", []):
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

    # Source distribution
    source_counts: dict[str, int] = {}
    for item in items:
        for source in item.get("source_types", []):
            source_counts[source] = source_counts.get(source, 0) + 1

    # Relevance distribution
    high_relevance = sum(1 for i in items if i["relevance_score"] >= 0.7)
    medium_relevance = sum(1 for i in items if 0.3 <= i["relevance_score"] < 0.7)

    return {
        "total_items": len(items),
        "persisted_count": state.get("persisted_count", 0),
        "collection_errors": len(state.get("collection_errors", [])),
        "topic_distribution": topic_counts,
        "source_distribution": source_counts,
        "relevance_breakdown": {
            "high": high_relevance,
            "medium": medium_relevance,
        },
    }


async def publish(state: AggregatorState) -> dict:
    """
    LangGraph node: Format and publish the final output.

    Creates a structured payload with:
    - Metadata about the run
    - Items grouped by topic
    - A flat list of all items
    - Summary statistics

    Args:
        state: Final graph state with all processed data

    Returns:
        Partial state update with publication_payload
    """
    items = state.get("processed_items", [])
    run_id = state.get("run_id", "unknown")
    run_date = state.get("run_date", datetime.now(UTC))

    logger.info("Creating publication payload", item_count=len(items))

    # Build the final payload
    payload = {
        # Metadata
        "meta": {
            "run_id": run_id,
            "run_date": run_date.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "version": "1.0",
        },
        # Statistics
        "stats": generate_summary_stats(state, items),
        # Items grouped by topic (for browsing)
        "by_topic": group_items_by_topic(items),
        # Flat list of all items (for iteration)
        "items": [format_item_for_api(item) for item in items],
        # Errors (for debugging)
        "errors": [
            {
                "source_type": e["source_type"],
                "source_id": e["source_id"],
                "error": e["error_message"],
            }
            for e in state.get("collection_errors", [])
        ],
    }

    logger.info(
        "Publication payload created",
        item_count=len(items),
        topic_count=len(payload["by_topic"]),
        error_count=len(payload["errors"]),
    )

    return {"publication_payload": payload}


def create_publish_node():
    """
    Factory function to create a publish node.

    This follows the same pattern as other nodes for consistency,
    even though publish doesn't need configuration.

    Usage:
        builder.add_node("publish", create_publish_node())
    """

    async def node(state: AggregatorState) -> dict:
        return await publish(state)

    return node
