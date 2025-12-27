"""
Tests for the deduplicate node.

Key testing strategies:
1. Test exact deduplication by item_id
2. Test merge behavior (content selection, metadata merging)
3. Test edge cases (empty input, single item, all duplicates)
4. Test sorting by date
"""

from datetime import UTC, datetime

import pytest

from aggregator.graph.nodes.deduplicate import (
    deduplicate,
    deduplicate_by_id,
    find_semantic_duplicates,
    merge_duplicate_items,
)
from aggregator.graph.state import RawItem


def make_raw_item(
    item_id: str = "abc123",
    title: str = "Test Article",
    content: str = "Test content",
    source_type: str = "rss",
    source_id: str = "https://example.com/feed",
    published_at: datetime | None = None,
    url: str | None = "https://example.com/article",
    author: str | None = "Test Author",
) -> RawItem:
    """Helper to create test RawItems."""
    return RawItem(
        item_id=item_id,
        title=title,
        content=content,
        source_type=source_type,
        source_id=source_id,
        published_at=published_at or datetime(2024, 12, 23, 10, 0, 0, tzinfo=UTC),
        url=url,
        author=author,
        raw_metadata={"feed_name": "Test Feed"},
    )


class TestMergeDuplicateItems:
    """Tests for the merge_duplicate_items function."""

    def test_single_item_unchanged(self):
        """Single item should pass through unchanged."""
        item = make_raw_item()
        result = merge_duplicate_items([item])
        assert result == item

    def test_keeps_longest_content(self):
        """Should keep the item with longest content."""
        short_item = make_raw_item(content="Short")
        long_item = make_raw_item(content="This is much longer content with more details")

        result = merge_duplicate_items([short_item, long_item])
        assert "much longer content" in result["content"]

    def test_merges_source_types(self):
        """Should track all source types in metadata."""
        rss_item = make_raw_item(source_type="rss", source_id="https://feed.com/rss")
        gmail_item = make_raw_item(source_type="gmail", source_id="newsletter@example.com")

        result = merge_duplicate_items([rss_item, gmail_item])

        # Check merged metadata
        assert "merged_from_sources" in result["raw_metadata"]
        assert set(result["raw_metadata"]["merged_from_sources"]) == {"rss", "gmail"}

    def test_uses_earliest_date(self):
        """Should use the earliest published_at date."""
        older = make_raw_item(
            published_at=datetime(2024, 12, 20, tzinfo=UTC),
            content="Older article",
        )
        newer = make_raw_item(
            published_at=datetime(2024, 12, 23, tzinfo=UTC),
            content="Newer article with more content",
        )

        result = merge_duplicate_items([newer, older])

        # Should use oldest date even though newer has longer content
        assert result["published_at"] == datetime(2024, 12, 20, tzinfo=UTC)
        # But should still use longer content
        assert "more content" in result["content"]

    def test_collects_all_urls(self):
        """Should collect all unique URLs."""
        item1 = make_raw_item(url="https://example.com/article")
        item2 = make_raw_item(url="https://mirror.com/same-article")

        result = merge_duplicate_items([item1, item2])

        assert "all_urls" in result["raw_metadata"]
        assert len(result["raw_metadata"]["all_urls"]) == 2

    def test_handles_none_urls(self):
        """Should handle items with None URLs gracefully."""
        with_url = make_raw_item(url="https://example.com/article")
        without_url = make_raw_item(url=None)

        result = merge_duplicate_items([with_url, without_url])

        # Should have the one valid URL
        assert result["url"] == "https://example.com/article"


class TestDeduplicateById:
    """Tests for the deduplicate_by_id function."""

    def test_no_duplicates(self):
        """Items with different IDs should all pass through."""
        items = [
            make_raw_item(item_id="a"),
            make_raw_item(item_id="b"),
            make_raw_item(item_id="c"),
        ]

        result = deduplicate_by_id(items)
        assert len(result) == 3

    def test_removes_exact_duplicates(self):
        """Items with same ID should be merged."""
        items = [
            make_raw_item(item_id="same", content="Short"),
            make_raw_item(item_id="same", content="This is the longer version"),
            make_raw_item(item_id="different"),
        ]

        result = deduplicate_by_id(items)
        assert len(result) == 2

        # Find the merged item
        merged = next(item for item in result if item["item_id"] == "same")
        assert "longer version" in merged["content"]

    def test_empty_list(self):
        """Empty input should return empty output."""
        result = deduplicate_by_id([])
        assert result == []

    def test_all_duplicates(self):
        """All items with same ID should merge to one."""
        items = [
            make_raw_item(item_id="same", source_type="rss"),
            make_raw_item(item_id="same", source_type="gmail"),
            make_raw_item(item_id="same", source_type="rss"),
        ]

        result = deduplicate_by_id(items)
        assert len(result) == 1


class TestDeduplicateNode:
    """Integration tests for the full deduplicate node."""

    async def test_returns_correct_shape(self):
        """Node should return dict with deduplicated_items."""
        state = {"raw_items": [make_raw_item()]}

        result = await deduplicate(state)

        assert "deduplicated_items" in result
        assert isinstance(result["deduplicated_items"], list)

    async def test_empty_state(self):
        """Should handle missing raw_items gracefully."""
        state = {}

        result = await deduplicate(state)

        assert result["deduplicated_items"] == []

    async def test_preserves_all_unique_items(self):
        """All unique items should be preserved."""
        state = {
            "raw_items": [
                make_raw_item(item_id="a", title="Article A"),
                make_raw_item(item_id="b", title="Article B"),
                make_raw_item(item_id="c", title="Article C"),
            ]
        }

        result = await deduplicate(state)

        assert len(result["deduplicated_items"]) == 3

    async def test_merges_duplicates(self):
        """Duplicate items should be merged."""
        state = {
            "raw_items": [
                make_raw_item(item_id="dup", source_type="rss"),
                make_raw_item(item_id="dup", source_type="gmail"),
                make_raw_item(item_id="unique"),
            ]
        }

        result = await deduplicate(state)

        assert len(result["deduplicated_items"]) == 2

    async def test_sorts_by_date_newest_first(self):
        """Results should be sorted by published_at, newest first."""
        state = {
            "raw_items": [
                make_raw_item(
                    item_id="old",
                    published_at=datetime(2024, 12, 20, tzinfo=UTC),
                ),
                make_raw_item(
                    item_id="new",
                    published_at=datetime(2024, 12, 25, tzinfo=UTC),
                ),
                make_raw_item(
                    item_id="middle",
                    published_at=datetime(2024, 12, 22, tzinfo=UTC),
                ),
            ]
        }

        result = await deduplicate(state)

        dates = [item["published_at"] for item in result["deduplicated_items"]]
        assert dates == sorted(dates, reverse=True)

    async def test_real_world_scenario(self):
        """Test a realistic scenario with mixed sources and duplicates."""
        state = {
            "raw_items": [
                # Same article from RSS and Gmail
                make_raw_item(
                    item_id="breaking-news",
                    title="Breaking: New AI Model Released",
                    source_type="rss",
                    source_id="https://techblog.com/feed",
                    content="Short RSS excerpt...",
                    published_at=datetime(2024, 12, 23, 10, 0, tzinfo=UTC),
                ),
                make_raw_item(
                    item_id="breaking-news",
                    title="Breaking: New AI Model Released",
                    source_type="gmail",
                    source_id="newsletter@techblog.com",
                    content="Full newsletter content with much more detail about the release...",
                    published_at=datetime(2024, 12, 23, 11, 0, tzinfo=UTC),
                ),
                # Unique article
                make_raw_item(
                    item_id="other-article",
                    title="Another Story",
                    source_type="rss",
                    published_at=datetime(2024, 12, 22, tzinfo=UTC),
                ),
            ]
        }

        result = await deduplicate(state)

        # Should have 2 items (merged + unique)
        assert len(result["deduplicated_items"]) == 2

        # Find the merged item
        merged = next(
            item for item in result["deduplicated_items"] if item["item_id"] == "breaking-news"
        )

        # Should have longer content from Gmail
        assert "much more detail" in merged["content"]

        # Should track both sources
        assert "merged_from_sources" in merged["raw_metadata"]
        assert set(merged["raw_metadata"]["merged_from_sources"]) == {"rss", "gmail"}

        # Should use earlier date (10:00 from RSS, not 11:00 from Gmail)
        assert merged["published_at"].hour == 10


class TestSemanticDuplicates:
    """Tests for the semantic duplicate detection placeholder."""

    def test_not_implemented(self):
        """Should raise NotImplementedError until embeddings are available."""
        with pytest.raises(NotImplementedError):
            find_semantic_duplicates([], [], 0.85)
