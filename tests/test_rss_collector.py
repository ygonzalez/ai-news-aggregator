"""
Tests for the RSS collector node.

Key testing strategies:
1. Mock HTTP responses using pytest-httpx (no real network calls)
2. Test date filtering logic
3. Test error handling for various failure modes
4. Test content extraction from different RSS formats
"""

from datetime import UTC, datetime

import httpx
import pytest

from aggregator.config import RssFeedConfig
from aggregator.graph.nodes.rss_collector import (
    extract_content,
    fetch_single_feed,
    generate_item_id,
    parse_published_date,
    rss_collector,
)

# Sample RSS feed for testing
SAMPLE_RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>A test feed</description>
    <item>
      <title>Recent Article</title>
      <link>https://example.com/recent</link>
      <description>This is a recent article about AI.</description>
      <pubDate>Mon, 23 Dec 2024 10:00:00 GMT</pubDate>
      <author>test@example.com</author>
    </item>
    <item>
      <title>Old Article</title>
      <link>https://example.com/old</link>
      <description>This is an old article.</description>
      <pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

# Atom feed format (different from RSS)
SAMPLE_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <entry>
    <title>Atom Article</title>
    <link href="https://example.com/atom-article"/>
    <id>urn:uuid:1234</id>
    <updated>2024-12-23T10:00:00Z</updated>
    <content type="html">&lt;p&gt;Full content here with &lt;b&gt;HTML&lt;/b&gt;&lt;/p&gt;</content>
    <summary>Short summary</summary>
  </entry>
</feed>
"""


class TestGenerateItemId:
    """Tests for the item ID generation function."""

    def test_same_url_same_id(self):
        """Same URL should always produce the same ID."""
        url = "https://example.com/article"
        id1 = generate_item_id(url, "Title 1", "Content 1")
        id2 = generate_item_id(url, "Title 2", "Content 2")
        assert id1 == id2  # URL takes precedence

    def test_different_urls_different_ids(self):
        """Different URLs should produce different IDs."""
        id1 = generate_item_id("https://example.com/a", "Title", "Content")
        id2 = generate_item_id("https://example.com/b", "Title", "Content")
        assert id1 != id2

    def test_fallback_without_url(self):
        """Without URL, should hash title + content."""
        id1 = generate_item_id(None, "Same Title", "Same Content")
        id2 = generate_item_id(None, "Same Title", "Same Content")
        assert id1 == id2

    def test_fallback_different_content(self):
        """Different content should produce different IDs when no URL."""
        id1 = generate_item_id(None, "Title", "Content A")
        id2 = generate_item_id(None, "Title", "Content B")
        assert id1 != id2


class TestParsedPublishedDate:
    """Tests for date parsing from feed entries."""

    def test_parse_rfc2822_date(self):
        """Should parse RFC 2822 format (common in RSS)."""
        entry = {"published": "Mon, 23 Dec 2024 10:00:00 GMT"}
        result = parse_published_date(entry)
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 23

    def test_parse_from_tuple(self):
        """Should parse pre-parsed time tuple."""
        entry = {"published_parsed": (2024, 12, 23, 10, 0, 0, 0, 358, 0)}
        result = parse_published_date(entry)
        assert result.year == 2024
        assert result.month == 12

    def test_fallback_to_updated(self):
        """Should fall back to 'updated' field if 'published' missing."""
        entry = {"updated": "Mon, 23 Dec 2024 10:00:00 GMT"}
        result = parse_published_date(entry)
        assert result.year == 2024

    def test_fallback_to_now(self):
        """Should return current time if no date found."""
        entry = {}
        result = parse_published_date(entry)
        # Should be recent (within last minute)
        assert (datetime.now(UTC) - result).total_seconds() < 60


class TestExtractContent:
    """Tests for content extraction from different feed formats."""

    def test_extract_from_content_list(self):
        """Should extract from Atom-style content list."""
        entry = {
            "content": [{"value": "Full article content here"}],
            "summary": "Short summary",
        }
        result = extract_content(entry)
        assert result == "Full article content here"

    def test_extract_from_summary(self):
        """Should extract from summary when content not available."""
        entry = {"summary": "This is the summary"}
        result = extract_content(entry)
        assert result == "This is the summary"

    def test_extract_from_description(self):
        """Should extract from description (older RSS style)."""
        entry = {"description": "This is the description"}
        result = extract_content(entry)
        assert result == "This is the description"

    def test_prefer_longest_content(self):
        """Should return the longest available content."""
        entry = {
            "summary": "Short",
            "description": "This is a much longer description with more details",
        }
        result = extract_content(entry)
        assert "much longer" in result

    def test_empty_when_no_content(self):
        """Should return empty string when no content found."""
        entry = {}
        result = extract_content(entry)
        assert result == ""


class TestFetchSingleFeed:
    """Tests for fetching and parsing a single feed."""

    @pytest.fixture
    def feed_config(self):
        return RssFeedConfig(name="Test Feed", url="https://example.com/feed.xml")

    async def test_successful_fetch(self, httpx_mock, feed_config):
        """Should parse items from a valid RSS feed."""
        httpx_mock.add_response(
            url="https://example.com/feed.xml",
            text=SAMPLE_RSS_FEED,
        )

        cutoff = datetime(2024, 12, 1, tzinfo=UTC)

        async with httpx.AsyncClient() as client:
            items, errors = await fetch_single_feed(client, feed_config, cutoff)

        assert len(errors) == 0
        assert len(items) == 1  # Only "Recent Article" is after cutoff
        assert items[0]["title"] == "Recent Article"
        assert items[0]["source_type"] == "rss"

    async def test_date_filtering(self, httpx_mock, feed_config):
        """Should filter out items before cutoff date."""
        httpx_mock.add_response(
            url="https://example.com/feed.xml",
            text=SAMPLE_RSS_FEED,
        )

        # Set cutoff to future - should filter out all items
        cutoff = datetime(2025, 1, 1, tzinfo=UTC)

        async with httpx.AsyncClient() as client:
            items, errors = await fetch_single_feed(client, feed_config, cutoff)

        assert len(items) == 0
        assert len(errors) == 0

    async def test_http_error_handling(self, httpx_mock, feed_config):
        """Should record error and continue when HTTP request fails."""
        httpx_mock.add_response(
            url="https://example.com/feed.xml",
            status_code=404,
        )

        cutoff = datetime(2024, 1, 1, tzinfo=UTC)

        async with httpx.AsyncClient() as client:
            items, errors = await fetch_single_feed(client, feed_config, cutoff)

        assert len(items) == 0
        assert len(errors) == 1
        assert errors[0]["error_type"] == "HTTPStatusError"
        assert "404" in errors[0]["error_message"]

    async def test_atom_feed_parsing(self, httpx_mock, feed_config):
        """Should handle Atom feed format."""
        httpx_mock.add_response(
            url="https://example.com/feed.xml",
            text=SAMPLE_ATOM_FEED,
        )

        cutoff = datetime(2024, 12, 1, tzinfo=UTC)

        async with httpx.AsyncClient() as client:
            items, errors = await fetch_single_feed(client, feed_config, cutoff)

        assert len(errors) == 0
        assert len(items) == 1
        assert items[0]["title"] == "Atom Article"
        # Should prefer full content over summary
        assert "Full content here" in items[0]["content"]


class TestRssCollector:
    """Integration tests for the full RSS collector node."""

    @pytest.fixture
    def test_feeds(self):
        """Create test feeds for isolated testing."""
        return [
            RssFeedConfig(name="Feed 1", url="https://feed1.example.com/rss"),
            RssFeedConfig(name="Feed 2", url="https://feed2.example.com/rss"),
        ]

    async def test_collector_returns_correct_shape(self, httpx_mock, test_feeds):
        """Collector should return dict with raw_items and collection_errors."""
        # Mock all feeds to return empty
        for feed in test_feeds:
            httpx_mock.add_response(
                url=feed.url,
                text='<?xml version="1.0"?><rss><channel></channel></rss>',
            )

        state = {
            "run_date": datetime.now(UTC),
            "backfill_days": 7,
        }

        result = await rss_collector(state, feeds=test_feeds)

        assert "raw_items" in result
        assert "collection_errors" in result
        assert isinstance(result["raw_items"], list)
        assert isinstance(result["collection_errors"], list)

    async def test_collector_handles_mixed_success_failure(self, httpx_mock, test_feeds):
        """Collector should continue when some feeds fail."""
        # First feed succeeds
        httpx_mock.add_response(
            url=test_feeds[0].url,
            text=SAMPLE_RSS_FEED,
        )

        # Second feed fails
        httpx_mock.add_response(url=test_feeds[1].url, status_code=500)

        state = {
            "run_date": datetime(2024, 12, 25, tzinfo=UTC),
            "backfill_days": 7,
        }

        result = await rss_collector(state, feeds=test_feeds)

        # Should have items from the successful feed
        assert len(result["raw_items"]) >= 1
        # Should have one error from the failed feed
        assert len(result["collection_errors"]) == 1

    async def test_collector_with_custom_feeds(self, httpx_mock):
        """Collector should use custom feeds when provided."""
        custom_feeds = [
            RssFeedConfig(name="Custom Feed", url="https://custom.example.com/rss"),
        ]

        httpx_mock.add_response(
            url="https://custom.example.com/rss",
            text=SAMPLE_RSS_FEED,
        )

        state = {
            "run_date": datetime(2024, 12, 25, tzinfo=UTC),
            "backfill_days": 7,
        }

        result = await rss_collector(state, feeds=custom_feeds)

        # Should have collected from custom feed
        assert len(result["raw_items"]) == 1
        assert result["raw_items"][0]["source_id"] == "https://custom.example.com/rss"
