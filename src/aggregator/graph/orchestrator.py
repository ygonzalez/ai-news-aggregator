"""
LangGraph Orchestrator - Wires all nodes into a complete pipeline.

This module:
1. Creates the StateGraph with all nodes
2. Defines the execution flow
3. Compiles the graph for execution
4. Provides a run() function to execute the pipeline

Pipeline Flow:
    START
      ↓
    RSS Collector ──→ (parallel execution would add Gmail here)
      ↓
    Deduplicate
      ↓
    Summarize
      ↓
    Persist
      ↓
    Publish
      ↓
    END

How LangGraph Works:
1. Each node is an async function that takes state and returns updates
2. The state schema (AggregatorState) defines the shape of data
3. Annotated reducers merge outputs from parallel nodes
4. Edges define the execution order
5. compile() validates and prepares the graph for execution

Usage:
    from aggregator.graph.orchestrator import run_aggregator

    # Simple usage
    result = await run_aggregator(backfill_days=7)

    # Or manually
    from aggregator.graph.orchestrator import create_graph, run_pipeline
    graph = create_graph()
    result = await run_pipeline(graph, backfill_days=7)
"""

import uuid
from datetime import datetime, timezone

import structlog
from langgraph.graph import END, START, StateGraph

from aggregator.graph.nodes import (
    deduplicate,
    persist,
    publish,
    rss_collector,
    summarize,
)
from aggregator.graph.state import AggregatorState

logger = structlog.get_logger()


def create_graph() -> StateGraph:
    """
    Create and compile the aggregator graph.

    The graph defines:
    1. What nodes exist (our async functions)
    2. What order they run in (edges)
    3. How state flows between them (via AggregatorState)

    Returns:
        Compiled StateGraph ready for execution

    How the graph is built:
    - StateGraph(AggregatorState) tells LangGraph the schema
    - add_node() registers each function as a node
    - add_edge() connects nodes in sequence
    - compile() validates everything and prepares for execution
    """
    logger.info("Creating aggregator graph")

    # ========================================
    # STEP 1: Initialize the graph with our state schema
    # The state schema tells LangGraph:
    # - What fields exist
    # - How to merge parallel outputs (via operator.add for lists)
    # ========================================
    builder = StateGraph(AggregatorState)

    # ========================================
    # STEP 2: Add all nodes
    # Each node is registered with a name and a function.
    # The function must:
    # - Accept state as first argument
    # - Return a dict with partial state updates
    # ========================================
    builder.add_node("rss_collector", rss_collector)
    builder.add_node("deduplicate", deduplicate)
    builder.add_node("summarize", summarize)
    builder.add_node("persist", persist)
    builder.add_node("publish", publish)

    # NOTE: If we had Gmail, we'd add it here:
    # builder.add_node("gmail_collector", gmail_collector)

    # ========================================
    # STEP 3: Add edges to define execution order
    # START is a special constant meaning "entry point"
    # END is a special constant meaning "exit point"
    # ========================================

    # Entry: Start with RSS collector
    builder.add_edge(START, "rss_collector")

    # Sequential flow through the pipeline
    builder.add_edge("rss_collector", "deduplicate")
    builder.add_edge("deduplicate", "summarize")
    builder.add_edge("summarize", "persist")
    builder.add_edge("persist", "publish")

    # Exit: Publish is the final node
    builder.add_edge("publish", END)

    # ========================================
    # STEP 4: Compile the graph
    # This:
    # - Validates all edges connect valid nodes
    # - Ensures no cycles (infinite loops)
    # - Optimizes execution
    # ========================================
    graph = builder.compile()

    logger.info("Graph compiled successfully")
    return graph


async def run_pipeline(
    graph: StateGraph,
    backfill_days: int = 0,
    run_id: str | None = None,
) -> dict:
    """
    Execute the aggregator pipeline.

    This function:
    1. Creates initial state with run_id and backfill_days
    2. Invokes the graph (runs all nodes in order)
    3. Returns the publication_payload from final state

    Args:
        graph: Compiled StateGraph from create_graph()
        backfill_days: How many days back to collect (0 = today only)
        run_id: Optional unique ID for this run (auto-generated if None)

    Returns:
        The publication_payload from the final state

    How ainvoke works:
    - Passes initial state to the first node
    - Each node's output is merged into the state
    - Returns the final state after all nodes complete
    """
    # Generate unique run ID if not provided
    if run_id is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        run_id = f"run_{timestamp}_{unique_suffix}"

    run_date = datetime.now(timezone.utc)

    logger.info(
        "Starting pipeline run",
        run_id=run_id,
        run_date=run_date.isoformat(),
        backfill_days=backfill_days,
    )

    # Initial state - this is what the first node receives
    initial_state: AggregatorState = {
        "run_id": run_id,
        "run_date": run_date,
        "backfill_days": backfill_days,
    }

    # Execute the graph
    # ainvoke() is the async method to run the graph
    # It returns the final state after all nodes complete
    final_state = await graph.ainvoke(initial_state)

    # Extract results for logging
    payload = final_state.get("publication_payload", {})
    stats = payload.get("stats", {})

    logger.info(
        "Pipeline run complete",
        run_id=run_id,
        items_processed=stats.get("total_items", 0),
        items_persisted=stats.get("persisted_count", 0),
        errors=stats.get("collection_errors", 0),
    )

    return payload


# ========================================
# CONVENIENCE API
# Caching and high-level functions for common use cases
# ========================================

# Cache the compiled graph (expensive to create repeatedly)
_cached_graph: StateGraph | None = None


def get_graph() -> StateGraph:
    """
    Get or create the compiled graph (cached).

    Why cache? Compiling the graph:
    - Validates all node connections
    - Creates internal execution structures
    - Should only be done once per process

    Returns:
        The compiled StateGraph
    """
    global _cached_graph

    if _cached_graph is None:
        _cached_graph = create_graph()

    return _cached_graph


async def run_aggregator(backfill_days: int = 0) -> dict:
    """
    High-level function to run the full aggregator pipeline.

    This is the main entry point for running the pipeline.
    It handles graph creation and execution in one call.

    Args:
        backfill_days: Days of historical data to collect
            - 0: Only items from today
            - 7: Items from the past week
            - 14: Initial backfill (two weeks)

    Returns:
        Publication payload with all processed items

    Example:
        result = await run_aggregator(backfill_days=7)
        print(f"Processed {len(result['items'])} items")

        for item in result['items']:
            print(f"- {item['title']}")
    """
    graph = get_graph()
    return await run_pipeline(graph, backfill_days=backfill_days)