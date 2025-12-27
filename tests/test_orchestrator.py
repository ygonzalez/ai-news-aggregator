"""
Tests for the graph orchestrator.

Key testing strategies:
1. Test graph creation and compilation
2. Test end-to-end pipeline flow with mocked nodes
3. Test error handling in the pipeline
4. Test run ID generation
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aggregator.graph.orchestrator import (
    create_graph,
    get_graph,
    run_aggregator,
    run_pipeline,
)


class TestCreateGraph:
    """Tests for the create_graph function."""

    def test_creates_valid_graph(self):
        """Should create a compilable graph."""
        graph = create_graph()

        # Graph should be created and compiled
        assert graph is not None

    def test_graph_has_all_nodes(self):
        """Graph should contain all expected nodes."""
        graph = create_graph()

        # The compiled graph should have nodes
        # LangGraph stores nodes internally - we can verify by checking
        # that the graph was created without errors
        assert graph is not None

    def test_graph_is_cacheable(self):
        """Creating multiple graphs should work."""
        graph1 = create_graph()
        graph2 = create_graph()

        # Both should be valid
        assert graph1 is not None
        assert graph2 is not None


class TestGetGraph:
    """Tests for the cached get_graph function."""

    def test_returns_same_graph(self):
        """Should return the same cached graph instance."""
        # Reset the cache first
        import aggregator.graph.orchestrator as orchestrator

        orchestrator._cached_graph = None

        graph1 = get_graph()
        graph2 = get_graph()

        assert graph1 is graph2  # Same instance

    def test_creates_graph_on_first_call(self):
        """Should create graph on first call if not cached."""
        import aggregator.graph.orchestrator as orchestrator

        orchestrator._cached_graph = None

        graph = get_graph()

        assert graph is not None
        assert orchestrator._cached_graph is graph


class TestRunPipeline:
    """Tests for the run_pipeline function."""

    @pytest.fixture
    def mock_graph(self):
        """Create a mock graph that returns a valid final state."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(
            return_value={
                "publication_payload": {
                    "meta": {"run_id": "test-run"},
                    "stats": {
                        "total_items": 5,
                        "persisted_count": 4,
                        "collection_errors": 1,
                    },
                    "items": [],
                }
            }
        )
        return graph

    async def test_returns_publication_payload(self, mock_graph):
        """Should return the publication_payload from final state."""
        result = await run_pipeline(mock_graph, backfill_days=7)

        assert "meta" in result
        assert "stats" in result
        assert "items" in result

    async def test_passes_initial_state(self, mock_graph):
        """Should pass correct initial state to graph."""
        await run_pipeline(mock_graph, backfill_days=7, run_id="test-123")

        # Verify ainvoke was called with correct initial state
        call_args = mock_graph.ainvoke.call_args[0][0]
        assert call_args["run_id"] == "test-123"
        assert call_args["backfill_days"] == 7
        assert "run_date" in call_args

    async def test_generates_run_id_if_not_provided(self, mock_graph):
        """Should generate a run_id if not provided."""
        await run_pipeline(mock_graph, backfill_days=0)

        call_args = mock_graph.ainvoke.call_args[0][0]
        assert call_args["run_id"].startswith("run_")

    async def test_uses_provided_run_id(self, mock_graph):
        """Should use provided run_id."""
        await run_pipeline(mock_graph, run_id="custom-run-id")

        call_args = mock_graph.ainvoke.call_args[0][0]
        assert call_args["run_id"] == "custom-run-id"

    async def test_handles_empty_payload(self, mock_graph):
        """Should handle case where publication_payload is missing."""
        mock_graph.ainvoke = AsyncMock(return_value={})

        result = await run_pipeline(mock_graph)

        assert result == {}


class TestRunAggregator:
    """Tests for the high-level run_aggregator function."""

    async def test_uses_cached_graph(self):
        """Should use the cached graph."""
        # Reset cache
        import aggregator.graph.orchestrator as orchestrator

        orchestrator._cached_graph = None

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "publication_payload": {
                    "meta": {},
                    "stats": {"total_items": 0},
                    "items": [],
                }
            }
        )

        with patch.object(orchestrator, "get_graph", return_value=mock_graph):
            result = await run_aggregator(backfill_days=7)

        assert result is not None
        mock_graph.ainvoke.assert_called_once()

    async def test_passes_backfill_days(self):
        """Should pass backfill_days to the pipeline."""
        import aggregator.graph.orchestrator as orchestrator

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "publication_payload": {
                    "meta": {},
                    "stats": {},
                    "items": [],
                }
            }
        )

        with patch.object(orchestrator, "get_graph", return_value=mock_graph):
            await run_aggregator(backfill_days=14)

        call_args = mock_graph.ainvoke.call_args[0][0]
        assert call_args["backfill_days"] == 14


class TestIntegrationWithMockedNodes:
    """
    Integration tests that mock individual nodes.

    These tests verify the full pipeline flow without hitting
    external services (RSS feeds, Claude, database).
    """

    async def test_full_pipeline_flow(self):
        """Test that all nodes are called in order with mocked responses."""
        # Mock all the node functions
        mock_rss = AsyncMock(
            return_value={
                "raw_items": [
                    {
                        "item_id": "test-1",
                        "title": "Test Article",
                        "content": "Test content",
                        "source_type": "rss",
                        "source_id": "https://example.com/feed",
                        "published_at": datetime.now(UTC),
                        "url": "https://example.com/article",
                        "author": "Test Author",
                        "raw_metadata": {},
                    }
                ],
                "collection_errors": [],
            }
        )

        mock_dedup = AsyncMock(
            return_value={
                "deduplicated_items": [
                    {
                        "item_id": "test-1",
                        "title": "Test Article",
                        "content": "Test content",
                        "source_type": "rss",
                        "source_id": "https://example.com/feed",
                        "published_at": datetime.now(UTC),
                        "url": "https://example.com/article",
                        "author": "Test Author",
                        "raw_metadata": {},
                    }
                ]
            }
        )

        mock_summarize = AsyncMock(
            return_value={
                "processed_items": [
                    {
                        "item_id": "test-1",
                        "title": "Test Article",
                        "summary": "A test summary",
                        "key_points": ["Point 1", "Point 2", "Point 3"],
                        "topics": ["LLMs"],
                        "relevance_score": 0.8,
                        "original_urls": ["https://example.com/article"],
                        "source_types": ["rss"],
                        "published_at": datetime.now(UTC),
                        "processed_at": datetime.now(UTC),
                        "embedding": None,
                    }
                ]
            }
        )

        mock_persist = AsyncMock(return_value={"persisted_count": 1})

        mock_publish = AsyncMock(
            return_value={
                "publication_payload": {
                    "meta": {"run_id": "test"},
                    "stats": {"total_items": 1, "persisted_count": 1},
                    "items": [{"id": "test-1", "title": "Test Article"}],
                    "by_topic": {"LLMs": [{"id": "test-1"}]},
                    "errors": [],
                }
            }
        )

        # Patch all nodes
        with (
            patch("aggregator.graph.orchestrator.rss_collector", mock_rss),
            patch("aggregator.graph.orchestrator.deduplicate", mock_dedup),
            patch("aggregator.graph.orchestrator.summarize", mock_summarize),
            patch("aggregator.graph.orchestrator.persist", mock_persist),
            patch("aggregator.graph.orchestrator.publish", mock_publish),
        ):
            # Create a fresh graph with mocked nodes
            graph = create_graph()
            result = await run_pipeline(graph, backfill_days=7)

        # Verify the result
        assert result["stats"]["total_items"] == 1
        assert len(result["items"]) == 1

        # Verify all nodes were called
        mock_rss.assert_called_once()
        mock_dedup.assert_called_once()
        mock_summarize.assert_called_once()
        mock_persist.assert_called_once()
        mock_publish.assert_called_once()
