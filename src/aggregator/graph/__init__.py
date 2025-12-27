"""
LangGraph pipeline for the news aggregator.

This package contains:
- state.py: State schemas (AggregatorState, RawItem, ProcessedItem)
- nodes/: Individual pipeline nodes
- orchestrator.py: Graph wiring and execution

Usage:
    from aggregator.graph import run_aggregator

    result = await run_aggregator(backfill_days=7)
"""

from aggregator.graph.orchestrator import create_graph, get_graph, run_aggregator, run_pipeline
from aggregator.graph.state import (
    TOPIC_CATEGORIES,
    AggregatorState,
    CollectionError,
    ProcessedItem,
    RawItem,
)

__all__ = [
    # Orchestration
    "create_graph",
    "get_graph",
    "run_aggregator",
    "run_pipeline",
    # State types
    "AggregatorState",
    "RawItem",
    "ProcessedItem",
    "CollectionError",
    "TOPIC_CATEGORIES",
]
