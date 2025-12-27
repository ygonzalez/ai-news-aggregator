"""
Tests for the publish node.

Key testing strategies:
1. Test output format (API-ready structure)
2. Test topic grouping
3. Test statistics generation
4. Test error inclusion
"""

from datetime import datetime, timezone

import pytest

from aggregator.graph.nodes.publish import (
    format_item_for_api,
    generate_summary_stats,
    group_items_by_topic,
    publish,
)
from aggregator.graph.state import ProcessedItem


def make_processed_item(
    item_id: str = "test-123",
    title: str = "Test Article",
    summary: str = "This is a test summary.",
    key_points: list[str] | None = None,
    topics: list[str] | None = None,
    relevance_score: float = 0.8,
    original_urls: list[str] | None = None,
    source_types: list[str] | None = None,
    published_at: datetime | None = None,
    processed_at: datetime | None = None,
) -> ProcessedItem:
    """Helper to create test ProcessedItems.

    Note: Using 'if x is None' instead of 'x or default' to properly
    handle empty lists being passed explicitly.
    """
    return ProcessedItem(
        item_id=item_id,
        title=title,
        summary=summary,
        key_points=["Point 1", "Point 2", "Point 3"] if key_points is None else key_points,
        topics=["LLMs", "Research"] if topics is None else topics,
        relevance_score=relevance_score,
        original_urls=["https://example.com/article"] if original_urls is None else original_urls,
        source_types=["rss"] if source_types is None else source_types,
        published_at=published_at or datetime(2024, 12, 23, 10, 0, 0, tzinfo=timezone.utc),
        processed_at=processed_at or datetime(2024, 12, 23, 12, 0, 0, tzinfo=timezone.utc),
        embedding=None,  # Not included in API output anyway
    )


class TestFormatItemForApi:
    """Tests for the format_item_for_api function."""

    def test_converts_datetimes_to_iso(self):
        """Should convert datetime objects to ISO strings."""
        item = make_processed_item(
            published_at=datetime(2024, 12, 23, 10, 0, 0, tzinfo=timezone.utc),
            processed_at=datetime(2024, 12, 23, 12, 0, 0, tzinfo=timezone.utc),
        )

        result = format_item_for_api(item)

        assert result["published_at"] == "2024-12-23T10:00:00+00:00"
        assert result["processed_at"] == "2024-12-23T12:00:00+00:00"

    def test_renames_fields_for_api(self):
        """Should rename internal fields to API-friendly names."""
        item = make_processed_item(
            item_id="abc123",
            original_urls=["https://a.com", "https://b.com"],
            source_types=["rss", "gmail"],
        )

        result = format_item_for_api(item)

        assert result["id"] == "abc123"  # Renamed from item_id
        assert result["urls"] == ["https://a.com", "https://b.com"]  # Renamed
        assert result["sources"] == ["rss", "gmail"]  # Renamed

    def test_excludes_embedding(self):
        """Should not include embedding in API output."""
        item = make_processed_item()
        item["embedding"] = [0.1] * 1536  # Large embedding

        result = format_item_for_api(item)

        assert "embedding" not in result

    def test_includes_all_content_fields(self):
        """Should include all content fields."""
        item = make_processed_item(
            title="Test Title",
            summary="Test Summary",
            key_points=["A", "B", "C"],
            topics=["LLMs"],
            relevance_score=0.9,
        )

        result = format_item_for_api(item)

        assert result["title"] == "Test Title"
        assert result["summary"] == "Test Summary"
        assert result["key_points"] == ["A", "B", "C"]
        assert result["topics"] == ["LLMs"]
        assert result["relevance_score"] == 0.9


class TestGroupItemsByTopic:
    """Tests for the group_items_by_topic function."""

    def test_groups_by_primary_topic(self):
        """Should group items by their first topic."""
        items = [
            make_processed_item(item_id="a", topics=["LLMs", "Research"]),
            make_processed_item(item_id="b", topics=["LLMs"]),
            make_processed_item(item_id="c", topics=["AI Safety"]),
        ]

        result = group_items_by_topic(items)

        assert "LLMs" in result
        assert "AI Safety" in result
        assert len(result["LLMs"]) == 2
        assert len(result["AI Safety"]) == 1

    def test_handles_empty_topics(self):
        """Should use 'Uncategorized' for items without topics."""
        items = [
            make_processed_item(item_id="a", topics=[]),
        ]

        result = group_items_by_topic(items)

        assert "Uncategorized" in result
        assert len(result["Uncategorized"]) == 1

    def test_sorts_within_groups(self):
        """Should sort items within each group by relevance."""
        items = [
            make_processed_item(item_id="low", topics=["LLMs"], relevance_score=0.5),
            make_processed_item(item_id="high", topics=["LLMs"], relevance_score=0.9),
            make_processed_item(item_id="mid", topics=["LLMs"], relevance_score=0.7),
        ]

        result = group_items_by_topic(items)

        scores = [item["relevance_score"] for item in result["LLMs"]]
        assert scores == [0.9, 0.7, 0.5]  # Descending order

    def test_empty_list(self):
        """Should return empty dict for empty input."""
        result = group_items_by_topic([])
        assert result == {}


class TestGenerateSummaryStats:
    """Tests for the generate_summary_stats function."""

    def test_counts_total_items(self):
        """Should count total items."""
        items = [
            make_processed_item(),
            make_processed_item(),
            make_processed_item(),
        ]
        state = {"processed_items": items}

        result = generate_summary_stats(state, items)

        assert result["total_items"] == 3

    def test_counts_topics(self):
        """Should count topic distribution."""
        items = [
            make_processed_item(topics=["LLMs", "Research"]),
            make_processed_item(topics=["LLMs"]),
            make_processed_item(topics=["AI Safety"]),
        ]
        state = {}

        result = generate_summary_stats(state, items)

        assert result["topic_distribution"]["LLMs"] == 2
        assert result["topic_distribution"]["Research"] == 1
        assert result["topic_distribution"]["AI Safety"] == 1

    def test_counts_sources(self):
        """Should count source distribution."""
        items = [
            make_processed_item(source_types=["rss"]),
            make_processed_item(source_types=["rss", "gmail"]),
            make_processed_item(source_types=["gmail"]),
        ]
        state = {}

        result = generate_summary_stats(state, items)

        assert result["source_distribution"]["rss"] == 2
        assert result["source_distribution"]["gmail"] == 2

    def test_categorizes_relevance(self):
        """Should categorize items by relevance level."""
        items = [
            make_processed_item(relevance_score=0.9),  # High
            make_processed_item(relevance_score=0.8),  # High
            make_processed_item(relevance_score=0.5),  # Medium
            make_processed_item(relevance_score=0.4),  # Medium
        ]
        state = {}

        result = generate_summary_stats(state, items)

        assert result["relevance_breakdown"]["high"] == 2
        assert result["relevance_breakdown"]["medium"] == 2

    def test_includes_persisted_count(self):
        """Should include persisted count from state."""
        state = {"persisted_count": 5}

        result = generate_summary_stats(state, [])

        assert result["persisted_count"] == 5

    def test_includes_error_count(self):
        """Should count collection errors."""
        state = {
            "collection_errors": [
                {"source_type": "rss", "error_message": "Error 1"},
                {"source_type": "rss", "error_message": "Error 2"},
            ]
        }

        result = generate_summary_stats(state, [])

        assert result["collection_errors"] == 2


class TestPublishNode:
    """Integration tests for the full publish node."""

    async def test_returns_correct_shape(self):
        """Should return dict with publication_payload."""
        state = {
            "processed_items": [make_processed_item()],
            "run_id": "test-run",
            "run_date": datetime.now(timezone.utc),
        }

        result = await publish(state)

        assert "publication_payload" in result
        assert isinstance(result["publication_payload"], dict)

    async def test_payload_has_all_sections(self):
        """Should include all required sections in payload."""
        state = {
            "processed_items": [make_processed_item()],
            "run_id": "test-run",
            "run_date": datetime.now(timezone.utc),
        }

        result = await publish(state)
        payload = result["publication_payload"]

        assert "meta" in payload
        assert "stats" in payload
        assert "by_topic" in payload
        assert "items" in payload
        assert "errors" in payload

    async def test_meta_section(self):
        """Should include metadata in meta section."""
        run_date = datetime(2024, 12, 23, 10, 0, 0, tzinfo=timezone.utc)
        state = {
            "processed_items": [],
            "run_id": "run-123",
            "run_date": run_date,
        }

        result = await publish(state)
        meta = result["publication_payload"]["meta"]

        assert meta["run_id"] == "run-123"
        assert meta["run_date"] == "2024-12-23T10:00:00+00:00"
        assert "generated_at" in meta
        assert meta["version"] == "1.0"

    async def test_includes_errors(self):
        """Should include collection errors in output."""
        state = {
            "processed_items": [],
            "run_id": "test",
            "run_date": datetime.now(timezone.utc),
            "collection_errors": [
                {
                    "source_type": "rss",
                    "source_id": "https://broken.com/feed",
                    "error_message": "Connection timeout",
                },
            ],
        }

        result = await publish(state)
        errors = result["publication_payload"]["errors"]

        assert len(errors) == 1
        assert errors[0]["source_type"] == "rss"
        assert errors[0]["error"] == "Connection timeout"

    async def test_empty_state(self):
        """Should handle empty state gracefully."""
        state = {}

        result = await publish(state)

        assert result["publication_payload"]["items"] == []
        assert result["publication_payload"]["by_topic"] == {}

    async def test_items_are_formatted(self):
        """Should format items for API in the flat list."""
        item = make_processed_item(
            item_id="abc",
            published_at=datetime(2024, 12, 23, tzinfo=timezone.utc),
        )
        state = {
            "processed_items": [item],
            "run_id": "test",
            "run_date": datetime.now(timezone.utc),
        }

        result = await publish(state)
        items = result["publication_payload"]["items"]

        assert len(items) == 1
        assert items[0]["id"] == "abc"  # Formatted field name
        assert items[0]["published_at"] == "2024-12-23T00:00:00+00:00"  # ISO string