"""
Summarize Node - Uses Claude to process news items.

This node:
1. Takes deduplicated RawItems
2. Calls Claude for each item to generate:
   - Summary (2-3 paragraphs)
   - Key points (3-5 bullets)
   - Topic classification
   - Article type (news/tutorial)
3. Optionally generates embeddings via OpenAI
4. Returns ProcessedItems ready for persistence

LangGraph Integration:
- Input: AggregatorState with deduplicated_items
- Output: {"processed_items": [...]}

Rate Limiting:
- Uses asyncio.Semaphore to limit concurrent API calls
- Configurable batch size for large backlogs
"""

import asyncio
from datetime import UTC, datetime

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field

from aggregator.config import get_settings
from aggregator.graph.state import (
    ARTICLE_TYPES,
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
        description="A concise, informative title for the article. "
        "Use the original title if appropriate, or generate one if missing."
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
    article_type: str = Field(
        description=f"The type of article. Must be one of: {ARTICLE_TYPES}. "
        "'news' = announcements, industry updates, product launches, events. "
        "'tutorial' = how-to guides, walkthroughs, educational content, code examples.",
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
- For key_points: provide exactly 3-5 distinct takeaways as separate strings in a JSON array
- For topics: use only values from the allowed list
- For article_type: classify as "news" or "tutorial"
  - "news": announcements, industry updates, product launches, company news, events, research papers
  - "tutorial": how-to guides, step-by-step walkthroughs, educational content, code examples, best practices guides
"""


async def summarize_single_item(
    item: RawItem,
    llm: ChatAnthropic,
    embeddings_model: OpenAIEmbeddings | None = None,
    max_retries: int = 2,
) -> ProcessedItem | None:
    """
    Process a single item with Claude with retry logic.

    Args:
        item: Raw item to process
        llm: Claude model with structured output
        embeddings_model: Optional OpenAI embeddings model
        max_retries: Number of retries on validation errors

    Returns:
        ProcessedItem or None if processing fails after all retries
    """
    from pydantic import ValidationError

    log = logger.bind(item_id=item["item_id"], title=item.get("title"))

    # Format prompt
    prompt = SUMMARIZE_PROMPT.format(
        title=item.get("title") or "No title",
        content=item["content"][:8000],  # Truncate very long content
        source_type=item["source_type"],
        source_id=item["source_id"],
        published_at=item["published_at"].isoformat(),
    )

    # Retry loop for transient validation errors
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            # Call Claude with structured output
            result: ArticleSummary = await llm.ainvoke(prompt)

            log.debug("Claude summarization complete", attempt=attempt)

            # Generate embedding if model provided
            embedding = None
            if embeddings_model:
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
                "article_type": result.article_type,
                "original_urls": original_urls,
                "source_types": source_types if isinstance(source_types, list) else [source_types],
                "published_at": item["published_at"],
                "processed_at": datetime.now(UTC),
                "embedding": embedding,
            }

            return processed

        except ValidationError as e:
            # Retry on validation errors (Claude returned wrong format)
            last_error = e
            if attempt < max_retries:
                log.warning("Validation error, retrying", attempt=attempt + 1, error=str(e)[:100])
                await asyncio.sleep(0.5)  # Brief delay before retry
            continue

        except Exception as e:
            # Don't retry on other errors (API errors, etc.)
            log.error("Failed to summarize item", error=str(e), error_type=type(e).__name__)
            return None

    # All retries exhausted
    log.error("Failed after retries", error=str(last_error), retries=max_retries)
    return None


async def summarize(
    state: AggregatorState,
    max_concurrent: int = 5,
    generate_embeddings: bool = True,
) -> dict:
    """
    LangGraph node: Summarize deduplicated items using Claude.

    Args:
        state: Current graph state with deduplicated_items
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

    # Filter out failures
    processed_items = []
    failed_count = 0

    for result in results:
        if result is None:
            failed_count += 1
        else:
            processed_items.append(result)

    # Sort by published date (newest first)
    processed_items.sort(key=lambda x: x["published_at"], reverse=True)

    logger.info(
        "Summarization complete",
        input_count=len(items),
        output_count=len(processed_items),
        failed=failed_count,
    )

    return {"processed_items": processed_items}


def create_summarize_node(
    max_concurrent: int = 5,
    generate_embeddings: bool = True,
):
    """
    Factory function to create a summarize node with custom settings.

    Usage:
        # In orchestrator.py
        builder.add_node("summarize", create_summarize_node(max_concurrent=10))

    Args:
        max_concurrent: Max concurrent API calls
        generate_embeddings: Whether to generate embeddings

    Returns:
        An async function compatible with LangGraph nodes.
    """

    async def node(state: AggregatorState) -> dict:
        return await summarize(
            state,
            max_concurrent=max_concurrent,
            generate_embeddings=generate_embeddings,
        )

    return node
