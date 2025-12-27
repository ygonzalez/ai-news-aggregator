"""
Tests for the persist node.

Key testing strategies:
1. Mock asyncpg pool and connections
2. Test upsert logic
3. Test error handling
4. Test transaction behavior

Note on mocking asyncpg:
- pool.acquire() returns an async context manager
- We need to mock both the pool and the connection it returns
- The transaction() method also returns an async context manager
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aggregator.graph.nodes.persist import (
    get_recent_items,
    persist,
    persist_single_item,
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
    embedding: list[float] | None = None,
) -> ProcessedItem:
    """Helper to create test ProcessedItems."""
    return ProcessedItem(
        item_id=item_id,
        title=title,
        summary=summary,
        # Use 'if x is None' to properly handle empty lists
        key_points=["Point 1", "Point 2", "Point 3"] if key_points is None else key_points,
        topics=["LLMs", "Research"] if topics is None else topics,
        relevance_score=relevance_score,
        original_urls=["https://example.com/article"] if original_urls is None else original_urls,
        source_types=["rss"] if source_types is None else source_types,
        published_at=published_at or datetime(2024, 12, 23, 10, 0, 0, tzinfo=UTC),
        processed_at=processed_at or datetime(2024, 12, 23, 12, 0, 0, tzinfo=UTC),
        embedding=embedding,
    )


@pytest.fixture
def mock_connection():
    """Create a mock asyncpg connection with transaction support."""
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value="test-123")
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()

    # Create async context manager for transaction
    @asynccontextmanager
    async def mock_transaction():
        yield

    conn.transaction = mock_transaction
    return conn


@pytest.fixture
def mock_pool(mock_connection):
    """Create a mock asyncpg pool with acquire() context manager."""
    pool = MagicMock()

    # Create async context manager for acquire
    @asynccontextmanager
    async def mock_acquire():
        yield mock_connection

    pool.acquire = mock_acquire
    return pool


class TestPersistSingleItem:
    """Tests for the persist_single_item function."""

    async def test_successful_persist(self, mock_connection):
        """Should return True on successful insert."""
        item = make_processed_item()

        result = await persist_single_item(mock_connection, item)

        assert result is True
        mock_connection.fetchval.assert_called_once()

    async def test_persist_with_embedding(self, mock_connection):
        """Should handle items with embeddings."""
        embedding = [0.1] * 1536
        item = make_processed_item(embedding=embedding)

        result = await persist_single_item(mock_connection, item)

        assert result is True
        # Verify embedding was passed (last argument)
        call_args = mock_connection.fetchval.call_args
        assert call_args[0][-1] == embedding

    async def test_persist_without_embedding(self, mock_connection):
        """Should handle items without embeddings (None)."""
        item = make_processed_item(embedding=None)

        result = await persist_single_item(mock_connection, item)

        assert result is True

    async def test_handles_database_error(self, mock_connection):
        """Should return False and log on database error."""
        mock_connection.fetchval = AsyncMock(side_effect=Exception("DB error"))
        item = make_processed_item()

        result = await persist_single_item(mock_connection, item)

        assert result is False

    async def test_converts_lists_to_json(self, mock_connection):
        """Should convert Python lists to JSON strings for JSONB columns."""
        item = make_processed_item(
            key_points=["Point A", "Point B"],
            topics=["LLMs"],
        )

        await persist_single_item(mock_connection, item)

        # Get the call arguments (SQL is arg 0, then positional params)
        call_args = mock_connection.fetchval.call_args[0]
        # SQL is first, then: item_id(1), title(2), summary(3), key_points(4), topics(5)
        assert call_args[4] == '["Point A", "Point B"]'  # key_points
        assert call_args[5] == '["LLMs"]'  # topics


class TestPersistNode:
    """Integration tests for the full persist node."""

    async def test_empty_state(self):
        """Should handle missing processed_items."""
        state = {}

        # Don't need pool mock for empty state (returns early)
        result = await persist(state)

        assert result["persisted_count"] == 0

    async def test_persists_all_items(self, mock_pool, mock_connection):
        """Should persist all items and return count."""
        items = [
            make_processed_item(item_id="a"),
            make_processed_item(item_id="b"),
            make_processed_item(item_id="c"),
        ]
        state = {
            "processed_items": items,
            "run_id": "test-run",
            "run_date": datetime.now(UTC),
        }

        async def mock_get_pool():
            return mock_pool

        with patch("aggregator.graph.nodes.persist.get_db_pool", mock_get_pool):
            result = await persist(state)

        assert result["persisted_count"] == 3

    async def test_counts_failed_items(self, mock_pool, mock_connection):
        """Should count failures correctly."""
        items = [
            make_processed_item(item_id="a"),
            make_processed_item(item_id="b"),  # This one will fail
            make_processed_item(item_id="c"),
        ]
        state = {
            "processed_items": items,
            "run_id": "test-run",
            "run_date": datetime.now(UTC),
        }

        # Mock: first and third succeed, second fails
        call_count = [0]

        async def mock_fetchval(*args):
            call_count[0] += 1
            if call_count[0] == 2:  # Second item
                raise Exception("DB error")
            return "success"

        mock_connection.fetchval = mock_fetchval

        async def mock_get_pool():
            return mock_pool

        with patch("aggregator.graph.nodes.persist.get_db_pool", mock_get_pool):
            result = await persist(state)

        # Only 2 out of 3 should be persisted
        assert result["persisted_count"] == 2

    async def test_creates_pipeline_run_record(self, mock_pool, mock_connection):
        """Should create/update pipeline run record."""
        state = {
            "processed_items": [make_processed_item()],
            "run_id": "test-run-123",
            "run_date": datetime(2024, 12, 23, tzinfo=UTC),
        }

        async def mock_get_pool():
            return mock_pool

        with patch("aggregator.graph.nodes.persist.get_db_pool", mock_get_pool):
            await persist(state)

        # Should have called execute at least twice (create run + update run)
        assert mock_connection.execute.call_count >= 2

    async def test_returns_correct_shape(self, mock_pool, mock_connection):
        """Should return dict with persisted_count."""
        state = {
            "processed_items": [make_processed_item()],
            "run_id": "test",
            "run_date": datetime.now(UTC),
        }

        async def mock_get_pool():
            return mock_pool

        with patch("aggregator.graph.nodes.persist.get_db_pool", mock_get_pool):
            result = await persist(state)

        assert "persisted_count" in result
        assert isinstance(result["persisted_count"], int)


class TestGetRecentItems:
    """Tests for the get_recent_items query function."""

    async def test_returns_items(self, mock_pool, mock_connection):
        """Should return items from database."""
        # Mock a database row
        mock_row = {
            "item_id": "test-123",
            "title": "Test Article",
            "summary": "Summary text",
            "key_points": '["Point 1", "Point 2"]',
            "topics": '["LLMs"]',
            "relevance_score": 0.8,
            "original_urls": '["https://example.com"]',
            "source_types": '["rss"]',
            "published_at": datetime(2024, 12, 23, tzinfo=UTC),
            "processed_at": datetime(2024, 12, 23, 12, 0, tzinfo=UTC),
        }
        mock_connection.fetch = AsyncMock(return_value=[mock_row])

        async def mock_get_pool():
            return mock_pool

        with patch("aggregator.graph.nodes.persist.get_db_pool", mock_get_pool):
            items = await get_recent_items(limit=10)

        assert len(items) == 1
        # JSONB fields should be parsed to lists
        assert items[0]["key_points"] == ["Point 1", "Point 2"]
        assert items[0]["topics"] == ["LLMs"]

    async def test_respects_limit(self, mock_pool, mock_connection):
        """Should pass limit to query."""
        mock_connection.fetch = AsyncMock(return_value=[])

        async def mock_get_pool():
            return mock_pool

        with patch("aggregator.graph.nodes.persist.get_db_pool", mock_get_pool):
            await get_recent_items(limit=5)

        # Check that limit was passed
        call_args = mock_connection.fetch.call_args[0]
        assert 5 in call_args

    async def test_filters_by_topic(self, mock_pool, mock_connection):
        """Should filter by topic when provided."""
        mock_connection.fetch = AsyncMock(return_value=[])

        async def mock_get_pool():
            return mock_pool

        with patch("aggregator.graph.nodes.persist.get_db_pool", mock_get_pool):
            await get_recent_items(topic="LLMs")

        # Check that topic was included in query
        call_args = mock_connection.fetch.call_args[0]
        assert '["LLMs"]' in call_args

    async def test_filters_by_relevance(self, mock_pool, mock_connection):
        """Should filter by minimum relevance."""
        mock_connection.fetch = AsyncMock(return_value=[])

        async def mock_get_pool():
            return mock_pool

        with patch("aggregator.graph.nodes.persist.get_db_pool", mock_get_pool):
            await get_recent_items(min_relevance=0.7)

        # Check that relevance was passed
        call_args = mock_connection.fetch.call_args[0]
        assert 0.7 in call_args
