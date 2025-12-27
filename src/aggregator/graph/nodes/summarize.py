"""
Summarize Node - Uses Claude to process news items.

This node:
1. Takes deduplicated RawItems
2. Calls Claude for each item to generate:
   - Summary (2-3 paragraphs)
   - Key points (3-5 bullets)
   - Topic classification
   - Relevance score
3. Optionally generates embeddings via OpenAI
4. Filters out low-relevance items (< 0.3)
5. Returns ProcessedItems ready for persistence

LangGraph Integration:
- Input: AggregatorState with deduplicated_items
- Output: {"processed_items": [...]}

Rate Limiting:
- Uses asyncio.Semaphore to limit concurrent API calls
- Configurable batch size for large backlogs
"""

import asyncio
from datetime import datetime, timezone

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field

from aggregator.config import get_settings
from aggregator.graph.state import (
    TOPIC_CATEGORIES,
    AggregatorState,
    ProcessedItem,
    RawItem,
)

logger = structlog.get_logger()


# === Pydantic Schema for Claude's Structured Output ===

class ArticleSummary(BaseModel):
    """Schema for Claude's structured output."""

    title: str = Field(
        description="A concise, informative title for the article. Use the original title if appropriate, or generate one if missing."
    )
    summary: str = Field(
        description="A 2-3 paragraph summary of the main content. Focus on key information, findings, or announcements."
    )
    key_points: list[str] = Field(
        description="3-5 bullet points capturing the most important takeaways.",
        min_length=3,
        max_length=5,
    )
    topics: list[str] = Field(
        description=f"1-3 topic categories from this list: {TOPIC_CATEGORIES}",
        min_length=1,
        max_length=3,
    )
    relevance_score: float = Field(
        description="Score from 0-1 indicating relevance to AI/ML practitioners. 0=not relevant, 0.3=marginally relevant, 0.7=relevant, 1.0=highly relevant.",
        ge=0.0,
        le=1.0,
    )


# === Prompt Template ===

SUMMARIZE_PROMPT = """You are an AI news analyst helping ML practitioners stay informed.
Analyze the following article and provide a structured summary.

ARTICLE TITLE: {title}
ARTICLE CONTENT:
{content}

SOURCE: {source_type} from {source_id}
PUBLISHED: {published_at}

Guidelines:
- Focus on practical implications for AI/ML practitioners
- Highlight technical details, new capabilities, or industry impact
- Be concise but comprehensive
- Score relevance based on usefulness to AI/ML practitioners:
  - 0.0-0.3: Off-topic or tangential (business news with no technical content)
  - 0.3-0.5: Marginally relevant (general tech news mentioning AI)
  - 0.5-0.7: Relevant (AI industry news, product announcements)
  - 0.7-1.0: Highly relevant (technical content, research, tools, best practices)
- Only use topics from the provided list
"""


async def summarize_single_item(
    item: RawItem,
    llm: ChatAnthropic,
    embeddings_model: OpenAIEmbeddings | None = None,
) -> ProcessedItem | None:
    """
    Process a single item with Claude.

    Args:
        item: Raw item to process
        llm: Claude model with structured output
        embeddings_model: Optional OpenAI embeddings model

    Returns:
        ProcessedItem or None if processing fails
    """
    log = logger.bind(item_id=item["item_id"], title=item.get("title"))

    try:
        # Format prompt
        prompt = SUMMARIZE_PROMPT.format(
            title=item.get("title") or "No title",
            content=item["content"][:8000],  # Truncate very long content
            source_type=item["source_type"],
            source_id=item["source_id"],
            published_at=item["published_at"].isoformat(),
        )

        # Call Claude with structured output
        result: ArticleSummary = await llm.ainvoke(prompt)

        log.debug("Claude summarization complete", relevance=result.relevance_score)

        # Generate embedding if model provided
        embedding = None
        if embeddings_model:
            # Combine title and summary for embedding
            text_for_embedding = f"{result.title}\n\n{result.summary}"
            embedding_result = await embeddings_model.aembed_query(text_for_embedding)
            embedding = embedding_result

        # Extract source info (may be merged from multiple sources)
        raw_metadata = item.get("raw_metadata", {})
        source_types = raw_metadata.get("merged_from_sources", [item["source_type"]])
        original_urls = raw_metadata.get("all_urls", [item["url"]] if item.get("url") else [])

        processed: ProcessedItem = {
            "item_id": item["item_id"],
            "title": result.title,
            "summary": result.summary,
            "key_points": result.key_points,
            "topics": result.topics,
            "relevance_score": result.relevance_score,
            "original_urls": original_urls,
            "source_types": source_types if isinstance(source_types, list) else [source_types],
            "published_at": item["published_at"],
            "processed_at": datetime.now(timezone.utc),
            "embedding": embedding,
        }

        return processed

    except Exception as e:
        log.error("Failed to summarize item", error=str(e), error_type=type(e).__name__)
        return None


async def summarize(
    state: AggregatorState,
    relevance_threshold: float = 0.3,
    max_concurrent: int = 5,
    generate_embeddings: bool = True,
) -> dict:
    """
    LangGraph node: Summarize deduplicated items using Claude.

    Args:
        state: Current graph state with deduplicated_items
        relevance_threshold: Minimum relevance score to keep (default 0.3)
        max_concurrent: Max concurrent API calls (default 5)
        generate_embeddings: Whether to generate OpenAI embeddings (default True)

    Returns:
        Partial state update with processed_items
    """
    items = state.get("deduplicated_items", [])

    logger.info("Starting summarization", item_count=len(items))

    if not items:
        logger.warning("No items to summarize")
        return {"processed_items": []}

    # Initialize models
    settings = get_settings()

    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=settings.anthropic_api_key.get_secret_value(),
        max_tokens=1024,
    ).with_structured_output(ArticleSummary)

    embeddings_model = None
    if generate_embeddings:
        embeddings_model = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=settings.openai_api_key.get_secret_value(),
        )

    # Process items with concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_semaphore(item: RawItem) -> ProcessedItem | None:
        async with semaphore:
            return await summarize_single_item(item, llm, embeddings_model)

    # Run all summarizations concurrently (with semaphore limiting)
    tasks = [process_with_semaphore(item) for item in items]
    results = await asyncio.gather(*tasks)

    # Filter out failures and low-relevance items
    processed_items = []
    filtered_count = 0
    failed_count = 0

    for result in results:
        if result is None:
            failed_count += 1
        elif result["relevance_score"] < relevance_threshold:
            filtered_count += 1
            logger.debug(
                "Filtered low-relevance item",
                item_id=result["item_id"],
                score=result["relevance_score"],
            )
        else:
            processed_items.append(result)

    # Sort by relevance (highest first)
    processed_items.sort(key=lambda x: x["relevance_score"], reverse=True)

    logger.info(
        "Summarization complete",
        input_count=len(items),
        output_count=len(processed_items),
        filtered_low_relevance=filtered_count,
        failed=failed_count,
    )

    return {"processed_items": processed_items}


def create_summarize_node(
    relevance_threshold: float = 0.3,
    max_concurrent: int = 5,
    generate_embeddings: bool = True,
):
    """
    Factory function to create a summarize node with custom settings.

    Usage:
        # In orchestrator.py
        builder.add_node("summarize", create_summarize_node(relevance_threshold=0.5))

    Args:
        relevance_threshold: Minimum relevance to keep
        max_concurrent: Max concurrent API calls
        generate_embeddings: Whether to generate embeddings

    Returns:
        An async function compatible with LangGraph nodes.
    """
    async def node(state: AggregatorState) -> dict:
        return await summarize(
            state,
            relevance_threshold=relevance_threshold,
            max_concurrent=max_concurrent,
            generate_embeddings=generate_embeddings,
        )

    return node