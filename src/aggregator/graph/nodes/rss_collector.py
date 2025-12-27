"""
RSS Collector Node - Fetches and parses RSS/Atom feeds.

This node:
1. Fetches each configured RSS feed using httpx (async HTTP)
2. Parses the feed using feedparser
3. Filters items within the backfill_days window
4. Converts feed entries to RawItem format
5. Handles errors gracefully (logs them, doesn't fail the pipeline)

LangGraph Integration:
- Input: AggregatorState with run_date, backfill_days
- Output: {"raw_items": [...], "collection_errors": [...]}
- The output is merged with other collectors via operator.add reducer

Configuration:
- Feeds are configured in aggregator.config.DEFAULT_RSS_FEEDS
- Can be overridden by passing feeds parameter (useful for testing)
"""

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx
import structlog

from aggregator.config import DEFAULT_RSS_FEEDS, RssFeedConfig
from aggregator.graph.state import AggregatorState, CollectionError, RawItem

logger = structlog.get_logger()


def generate_item_id(url: str | None, title: str | None, content: str) -> str:
    """
    Generate a unique ID for an item.

    Uses URL if available (most reliable), otherwise hashes title + content.
    This ID is used for deduplication and database primary key.
    """
    if url:
        return hashlib.sha256(url.encode()).hexdigest()[:32]
    # Fallback: hash title + first 500 chars of content
    text = f"{title or ''}{content[:500]}"
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def parse_published_date(entry: dict) -> datetime:
    """
    Extract publication date from a feed entry.

    RSS feeds store dates in various fields and formats:
    - published_parsed: Pre-parsed tuple (most reliable)
    - published: RFC 2822 string
    - updated_parsed/updated: Fallback for Atom feeds

    Returns UTC datetime, or current time if parsing fails.
    """
    # Try pre-parsed dates first (feedparser converts these)
    for field in ["published_parsed", "updated_parsed"]:
        if parsed := entry.get(field):
            try:
                # Convert time tuple to datetime
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue

    # Try string dates
    for field in ["published", "updated"]:
        if date_str := entry.get(field):
            try:
                return parsedate_to_datetime(date_str)
            except (TypeError, ValueError):
                continue

    # Fallback: use current time (item will be included in results)
    logger.warning("Could not parse date, using current time", entry_title=entry.get("title"))
    return datetime.now(timezone.utc)


def extract_content(entry: dict) -> str:
    """
    Extract the main content from a feed entry.

    RSS feeds store content in various fields with different formats:
    - content: List of content objects (Atom style)
    - summary: Plain text or HTML summary
    - description: Older RSS style

    Returns the longest available content.
    """
    candidates = []

    # Atom-style content (list of content objects)
    if content_list := entry.get("content"):
        for content_obj in content_list:
            if value := content_obj.get("value"):
                candidates.append(value)

    # Summary/description fields
    for field in ["summary", "description"]:
        if value := entry.get(field):
            candidates.append(value)

    # Return the longest content (usually has the most information)
    if candidates:
        return max(candidates, key=len)

    return ""


async def fetch_single_feed(
    client: httpx.AsyncClient,
    feed_config: RssFeedConfig,
    cutoff_date: datetime,
) -> tuple[list[RawItem], list[CollectionError]]:
    """
    Fetch and parse a single RSS feed.

    Args:
        client: Shared httpx client (for connection pooling)
        feed_config: RssFeedConfig with name and url
        cutoff_date: Only include items published after this date

    Returns:
        Tuple of (items, errors) - errors are non-fatal
    """
    feed_url = feed_config.url
    feed_name = feed_config.name
    items: list[RawItem] = []
    errors: list[CollectionError] = []

    log = logger.bind(feed_name=feed_name, feed_url=feed_url)

    try:
        # Fetch the feed with timeout
        log.info("Fetching RSS feed")
        response = await client.get(feed_url, timeout=30.0)
        response.raise_for_status()

        # Parse the feed
        feed = feedparser.parse(response.text)

        if feed.bozo and feed.bozo_exception:
            # feedparser sets 'bozo' flag for malformed feeds
            # We still try to use what we can parse
            log.warning("Feed has parse errors", error=str(feed.bozo_exception))

        # Process entries
        for entry in feed.entries:
            published = parse_published_date(entry)

            # Skip items older than cutoff
            if published < cutoff_date:
                continue

            content = extract_content(entry)
            if not content:
                log.debug("Skipping entry with no content", title=entry.get("title"))
                continue

            item: RawItem = {
                "source_type": "rss",
                "source_id": feed_url,
                "item_id": generate_item_id(entry.get("link"), entry.get("title"), content),
                "title": entry.get("title"),
                "content": content,
                "author": entry.get("author"),
                "published_at": published,
                "url": entry.get("link"),
                "raw_metadata": {
                    "feed_name": feed_name,
                    "feed_title": feed.feed.get("title"),
                    "entry_id": entry.get("id"),
                    "tags": [tag.term for tag in entry.get("tags", [])],
                },
            }
            items.append(item)

        log.info("Feed processed", item_count=len(items))

    except httpx.HTTPStatusError as e:
        log.error("HTTP error fetching feed", status_code=e.response.status_code)
        errors.append(
            CollectionError(
                source_type="rss",
                source_id=feed_url,
                error_type="HTTPStatusError",
                error_message=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
                timestamp=datetime.now(timezone.utc),
            )
        )

    except httpx.RequestError as e:
        log.error("Request error fetching feed", error=str(e))
        errors.append(
            CollectionError(
                source_type="rss",
                source_id=feed_url,
                error_type=type(e).__name__,
                error_message=str(e),
                timestamp=datetime.now(timezone.utc),
            )
        )

    except Exception as e:
        log.exception("Unexpected error processing feed")
        errors.append(
            CollectionError(
                source_type="rss",
                source_id=feed_url,
                error_type=type(e).__name__,
                error_message=str(e),
                timestamp=datetime.now(timezone.utc),
            )
        )

    return items, errors


async def rss_collector(
    state: AggregatorState,
    feeds: list[RssFeedConfig] | None = None,
) -> dict:
    """
    LangGraph node: Collect items from all configured RSS feeds.

    This is the main entry point called by the LangGraph orchestrator.
    It fetches all feeds concurrently using asyncio.gather().

    Args:
        state: Current graph state with run_date and backfill_days
        feeds: Optional list of feeds to collect (defaults to DEFAULT_RSS_FEEDS).
               Pass custom feeds for testing or dynamic configuration.

    Returns:
        Partial state update with raw_items and collection_errors
    """
    # Use provided feeds or fall back to defaults
    feeds_to_collect = feeds if feeds is not None else DEFAULT_RSS_FEEDS

    run_date = state.get("run_date", datetime.now(timezone.utc))
    backfill_days = state.get("backfill_days", 0)

    # Calculate cutoff date for filtering
    cutoff_date = run_date - timedelta(days=backfill_days)

    logger.info(
        "Starting RSS collection",
        run_date=run_date.isoformat(),
        backfill_days=backfill_days,
        cutoff_date=cutoff_date.isoformat(),
        feed_count=len(feeds_to_collect),
    )

    all_items: list[RawItem] = []
    all_errors: list[CollectionError] = []

    # Use a shared client for connection pooling
    async with httpx.AsyncClient(
        headers={"User-Agent": "AI-News-Aggregator/1.0"},
        follow_redirects=True,
    ) as client:
        # Fetch all feeds concurrently
        tasks = [fetch_single_feed(client, feed, cutoff_date) for feed in feeds_to_collect]
        results = await asyncio.gather(*tasks)

        # Collect results
        for items, errors in results:
            all_items.extend(items)
            all_errors.extend(errors)

    logger.info(
        "RSS collection complete",
        total_items=len(all_items),
        total_errors=len(all_errors),
    )

    # Return partial state update (LangGraph merges this)
    return {
        "raw_items": all_items,
        "collection_errors": all_errors,
    }


def create_rss_collector_node(feeds: list[RssFeedConfig] | None = None):
    """
    Factory function to create an RSS collector node with custom feeds.

    This is useful when you need to wire the node into LangGraph with
    specific feeds (e.g., for testing or different environments).

    Usage:
        # In orchestrator.py
        builder.add_node("rss_collector", create_rss_collector_node(custom_feeds))

    Args:
        feeds: Custom feeds to use. Defaults to DEFAULT_RSS_FEEDS if None.

    Returns:
        An async function compatible with LangGraph nodes.
    """
    async def node(state: AggregatorState) -> dict:
        return await rss_collector(state, feeds=feeds)

    return node