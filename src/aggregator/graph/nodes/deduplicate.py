"""
Deduplicate Node - Removes duplicate items from collected news.

This node handles two types of deduplication:
1. Exact match: Items with the same item_id (URL hash) are merged
2. Semantic similarity: Items about the same topic (future - requires embeddings)

LangGraph Integration:
- Input: AggregatorState with raw_items from collectors
- Output: {"deduplicated_items": [...]}

Merging Strategy:
When multiple sources have the same item, we:
- Keep the longest content (usually has more detail)
- Preserve all source references (for attribution)
- Use the earliest published_at date
- Merge raw_metadata from all sources
"""

import structlog

from aggregator.graph.state import AggregatorState, RawItem

logger = structlog.get_logger()


def merge_duplicate_items(items: list[RawItem]) -> RawItem:
    """
    Merge multiple items with the same item_id into a single item.

    This preserves information from all sources while avoiding duplication.
    For example, if the same article is in RSS and Gmail, we want to know
    it came from both sources.

    Args:
        items: List of items with the same item_id

    Returns:
        A single merged RawItem
    """
    if len(items) == 1:
        return items[0]

    # Sort by content length (descending) to prefer richest content
    sorted_items = sorted(items, key=lambda x: len(x.get("content", "")), reverse=True)
    primary = sorted_items[0]

    # Collect all unique sources
    source_types = list({item["source_type"] for item in items})
    source_ids = list({item["source_id"] for item in items})

    # Collect all URLs (some items might have different URLs for same content)
    urls = list({item["url"] for item in items if item.get("url")})

    # Use earliest published date
    published_dates = [item["published_at"] for item in items]
    earliest_date = min(published_dates)

    # Merge raw_metadata from all sources
    merged_metadata = {}
    for item in items:
        source_key = f"{item['source_type']}:{item['source_id']}"
        merged_metadata[source_key] = item.get("raw_metadata", {})

    # Create merged item
    merged: RawItem = {
        "source_type": primary["source_type"],  # Primary source type
        "source_id": primary["source_id"],  # Primary source ID
        "item_id": primary["item_id"],
        "title": primary.get("title"),
        "content": primary["content"],
        "author": primary.get("author"),
        "published_at": earliest_date,
        "url": urls[0] if urls else None,
        "raw_metadata": {
            "merged_from_sources": source_types,
            "merged_from_ids": source_ids,
            "all_urls": urls,
            "source_metadata": merged_metadata,
        },
    }

    logger.info(
        "Merged duplicate items",
        item_id=primary["item_id"],
        source_count=len(items),
        sources=source_types,
    )

    return merged


def deduplicate_by_id(items: list[RawItem]) -> list[RawItem]:
    """
    Group items by item_id and merge duplicates.

    This is "exact" deduplication - items are only considered duplicates
    if they have the same item_id (which is typically a hash of the URL).

    Args:
        items: List of raw items from collectors

    Returns:
        List of deduplicated items
    """
    # Group items by item_id
    grouped: dict[str, list[RawItem]] = {}
    for item in items:
        item_id = item["item_id"]
        if item_id not in grouped:
            grouped[item_id] = []
        grouped[item_id].append(item)

    # Merge each group
    deduplicated = []
    duplicate_count = 0

    for item_id, group in grouped.items():
        if len(group) > 1:
            duplicate_count += len(group) - 1
        deduplicated.append(merge_duplicate_items(group))

    logger.info(
        "Exact deduplication complete",
        original_count=len(items),
        deduplicated_count=len(deduplicated),
        duplicates_merged=duplicate_count,
    )

    return deduplicated


async def deduplicate(state: AggregatorState) -> dict:
    """
    LangGraph node: Deduplicate collected items.

    Currently implements:
    1. Exact deduplication by item_id (URL hash)

    Future enhancements (when embeddings are available):
    2. Semantic similarity detection for near-duplicates
    3. Clustering of related articles about the same event

    Args:
        state: Current graph state with raw_items

    Returns:
        Partial state update with deduplicated_items
    """
    raw_items = state.get("raw_items", [])

    logger.info("Starting deduplication", item_count=len(raw_items))

    if not raw_items:
        logger.warning("No items to deduplicate")
        return {"deduplicated_items": []}

    # Phase 1: Exact deduplication by item_id
    deduplicated = deduplicate_by_id(raw_items)

    # Phase 2: Semantic similarity (placeholder for future)
    # When we have embeddings, we can:
    # 1. Compute pairwise cosine similarity
    # 2. Cluster items above a threshold (e.g., 0.85)
    # 3. Merge clusters into single items
    #
    # This would catch cases like:
    # - Same press release covered by multiple outlets
    # - Slightly different headlines for the same story
    # - Reworded/summarized versions of original articles

    # Sort by published date (newest first)
    deduplicated.sort(key=lambda x: x["published_at"], reverse=True)

    logger.info(
        "Deduplication complete",
        input_count=len(raw_items),
        output_count=len(deduplicated),
        reduction_pct=round((1 - len(deduplicated) / len(raw_items)) * 100, 1) if raw_items else 0,
    )

    return {"deduplicated_items": deduplicated}


def find_semantic_duplicates(
    items: list[RawItem],
    embeddings: list[list[float]],
    similarity_threshold: float = 0.85,
) -> list[list[int]]:
    """
    Find groups of semantically similar items using cosine similarity.

    This is a placeholder for future implementation when we add embeddings.
    It would be called after exact deduplication to find near-duplicates.

    Args:
        items: List of items (after exact deduplication)
        embeddings: List of embedding vectors (same order as items)
        similarity_threshold: Minimum cosine similarity to consider items related

    Returns:
        List of index groups where each group contains semantically similar items
    """
    # TODO: Implement when embeddings are available
    # Algorithm:
    # 1. Compute pairwise cosine similarities (O(n^2) but n is small after filtering)
    # 2. Build a graph where edges connect items above threshold
    # 3. Find connected components (these are our duplicate groups)
    #
    # For efficiency with large datasets:
    # - Use approximate nearest neighbors (e.g., FAISS, Annoy)
    # - Or leverage pgvector's indexing capabilities
    raise NotImplementedError("Semantic deduplication requires embeddings - coming in Phase 4")
