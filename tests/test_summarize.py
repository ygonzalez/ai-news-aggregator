"""
Tests for the summarize node.

Key testing strategies:
1. Mock Claude API calls to avoid real API usage
2. Test structured output parsing
3. Test relevance filtering
4. Test embedding generation
5. Test error handling
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aggregator.graph.nodes.summarize import (
    ArticleSummary,
    summarize,
    summarize_single_item,
)
from aggregator.graph.state import RawItem


def make_raw_item(
    item_id: str = "test-123",
    title: str = "Test AI Article",
    content: str = "This article discusses the latest developments in AI.",
    source_type: str = "rss",
    source_id: str = "https://example.com/feed",
    published_at: datetime | None = None,
    url: str = "https://example.com/article",
) -> RawItem:
    """Helper to create test RawItems."""
    return RawItem(
        item_id=item_id,
        title=title,
        content=content,
        source_type=source_type,
        source_id=source_id,
        published_at=published_at or datetime(2024, 12, 23, 10, 0, 0, tzinfo=timezone.utc),
        url=url,
        author="Test Author",
        raw_metadata={"feed_name": "Test Feed"},
    )


def make_article_summary(
    title: str = "AI Breakthrough Summary",
    summary: str = "This article discusses important AI developments.",
    key_points: list[str] | None = None,
    topics: list[str] | None = None,
    relevance_score: float = 0.8,
) -> ArticleSummary:
    """Helper to create test ArticleSummary objects."""
    return ArticleSummary(
        title=title,
        summary=summary,
        key_points=key_points or ["Point 1", "Point 2", "Point 3"],
        topics=topics or ["LLMs", "Research"],
        relevance_score=relevance_score,
    )


@pytest.fixture
def mock_settings():
    """Mock settings to avoid requiring real API keys."""
    with patch("aggregator.graph.nodes.summarize.get_settings") as mock:
        settings = MagicMock()
        settings.anthropic_api_key.get_secret_value.return_value = "test-anthropic-key"
        settings.openai_api_key.get_secret_value.return_value = "test-openai-key"
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_llm():
    """Mock Claude LLM that returns structured output."""
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=make_article_summary())
    return llm


@pytest.fixture
def mock_embeddings():
    """Mock OpenAI embeddings model."""
    embeddings = AsyncMock()
    # Return a mock 1536-dim embedding
    embeddings.aembed_query = AsyncMock(return_value=[0.1] * 1536)
    return embeddings


class TestArticleSummary:
    """Tests for the Pydantic schema."""

    def test_valid_summary(self):
        """Should accept valid summary data."""
        summary = ArticleSummary(
            title="Test Title",
            summary="Test summary text.",
            key_points=["Point 1", "Point 2", "Point 3"],
            topics=["LLMs"],
            relevance_score=0.75,
        )
        assert summary.title == "Test Title"
        assert len(summary.key_points) == 3

    def test_relevance_bounds(self):
        """Relevance score should be between 0 and 1."""
        with pytest.raises(ValueError):
            ArticleSummary(
                title="Test",
                summary="Test",
                key_points=["A", "B", "C"],
                topics=["LLMs"],
                relevance_score=1.5,  # Invalid: > 1
            )

    def test_key_points_minimum(self):
        """Should require at least 3 key points."""
        with pytest.raises(ValueError):
            ArticleSummary(
                title="Test",
                summary="Test",
                key_points=["Only one"],  # Invalid: < 3
                topics=["LLMs"],
                relevance_score=0.5,
            )


class TestSummarizeSingleItem:
    """Tests for the single item summarization function."""

    async def test_successful_summarization(self, mock_llm):
        """Should return ProcessedItem on success."""
        item = make_raw_item()

        result = await summarize_single_item(item, mock_llm, None)

        assert result is not None
        assert result["item_id"] == "test-123"
        assert result["title"] == "AI Breakthrough Summary"
        assert len(result["key_points"]) == 3

    async def test_with_embeddings(self, mock_llm, mock_embeddings):
        """Should include embedding when model provided."""
        item = make_raw_item()

        result = await summarize_single_item(item, mock_llm, mock_embeddings)

        assert result is not None
        assert result["embedding"] is not None
        assert len(result["embedding"]) == 1536

    async def test_without_embeddings(self, mock_llm):
        """Should set embedding to None when no model provided."""
        item = make_raw_item()

        result = await summarize_single_item(item, mock_llm, None)

        assert result is not None
        assert result["embedding"] is None

    async def test_preserves_timestamps(self, mock_llm):
        """Should preserve published_at and add processed_at."""
        original_time = datetime(2024, 12, 20, 10, 0, 0, tzinfo=timezone.utc)
        item = make_raw_item(published_at=original_time)

        result = await summarize_single_item(item, mock_llm, None)

        assert result["published_at"] == original_time
        assert result["processed_at"] is not None
        assert result["processed_at"] > original_time

    async def test_handles_merged_sources(self, mock_llm):
        """Should handle items merged from multiple sources."""
        item = make_raw_item()
        item["raw_metadata"] = {
            "merged_from_sources": ["rss", "gmail"],
            "all_urls": ["https://a.com", "https://b.com"],
        }

        result = await summarize_single_item(item, mock_llm, None)

        assert result["source_types"] == ["rss", "gmail"]
        assert len(result["original_urls"]) == 2

    async def test_handles_llm_error(self, mock_llm):
        """Should return None on LLM error."""
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("API error"))
        item = make_raw_item()

        result = await summarize_single_item(item, mock_llm, None)

        assert result is None


class TestSummarizeNode:
    """Integration tests for the full summarize node."""

    async def test_empty_state(self, mock_settings):
        """Should handle missing deduplicated_items."""
        state = {}

        # Mock the LLM initialization
        with patch("aggregator.graph.nodes.summarize.ChatAnthropic") as mock_claude:
            mock_claude.return_value.with_structured_output.return_value = MagicMock()

            result = await summarize(state, generate_embeddings=False)

        assert result["processed_items"] == []

    async def test_filters_low_relevance(self, mock_settings):
        """Should filter items below relevance threshold."""
        items = [
            make_raw_item(item_id="high", title="High relevance"),
            make_raw_item(item_id="low", title="Low relevance"),
        ]

        # Mock LLM to return different relevance scores
        mock_llm = MagicMock()

        async def mock_invoke(prompt):
            if "High relevance" in prompt:
                return make_article_summary(relevance_score=0.8)
            else:
                return make_article_summary(relevance_score=0.2)

        mock_llm.ainvoke = mock_invoke

        with patch("aggregator.graph.nodes.summarize.ChatAnthropic") as mock_claude:
            mock_claude.return_value.with_structured_output.return_value = mock_llm

            state = {"deduplicated_items": items}
            result = await summarize(state, relevance_threshold=0.3, generate_embeddings=False)

        # Only high relevance item should remain
        assert len(result["processed_items"]) == 1
        assert result["processed_items"][0]["relevance_score"] == 0.8

    async def test_sorts_by_relevance(self, mock_settings):
        """Should sort results by relevance (highest first)."""
        items = [
            make_raw_item(item_id="a"),
            make_raw_item(item_id="b"),
            make_raw_item(item_id="c"),
        ]

        # Return different relevance scores
        call_count = [0]
        scores = [0.5, 0.9, 0.7]

        async def mock_invoke(prompt):
            score = scores[call_count[0]]
            call_count[0] += 1
            return make_article_summary(relevance_score=score)

        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_invoke

        with patch("aggregator.graph.nodes.summarize.ChatAnthropic") as mock_claude:
            mock_claude.return_value.with_structured_output.return_value = mock_llm

            state = {"deduplicated_items": items}
            result = await summarize(state, relevance_threshold=0.0, generate_embeddings=False)

        scores = [item["relevance_score"] for item in result["processed_items"]]
        assert scores == sorted(scores, reverse=True)

    async def test_respects_concurrency_limit(self, mock_settings):
        """Should limit concurrent API calls."""
        items = [make_raw_item(item_id=str(i)) for i in range(10)]

        concurrent_calls = [0]
        max_concurrent_seen = [0]

        async def mock_invoke(prompt):
            concurrent_calls[0] += 1
            max_concurrent_seen[0] = max(max_concurrent_seen[0], concurrent_calls[0])
            await asyncio.sleep(0.01)  # Small delay to test concurrency
            concurrent_calls[0] -= 1
            return make_article_summary()

        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_invoke

        with patch("aggregator.graph.nodes.summarize.ChatAnthropic") as mock_claude:
            mock_claude.return_value.with_structured_output.return_value = mock_llm

            state = {"deduplicated_items": items}
            await summarize(state, max_concurrent=3, generate_embeddings=False)

        # Should never exceed max_concurrent
        assert max_concurrent_seen[0] <= 3

    async def test_returns_correct_shape(self, mock_settings):
        """Should return dict with processed_items."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=make_article_summary())

        with patch("aggregator.graph.nodes.summarize.ChatAnthropic") as mock_claude:
            mock_claude.return_value.with_structured_output.return_value = mock_llm

            state = {"deduplicated_items": [make_raw_item()]}
            result = await summarize(state, generate_embeddings=False)

        assert "processed_items" in result
        assert isinstance(result["processed_items"], list)
        assert len(result["processed_items"]) == 1