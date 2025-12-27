"""
LangGraph nodes for the news aggregator pipeline.

Each node is an async function that:
- Takes AggregatorState as input
- Returns a dict with partial state updates
- Handles errors gracefully (logs but doesn't crash)

Nodes:
- rss_collector: Fetch and parse RSS feeds
- deduplicate: Remove duplicate items
- summarize: Process items with Claude
- persist: Save to PostgreSQL
- publish: Format final output
"""

from aggregator.graph.nodes.deduplicate import deduplicate
from aggregator.graph.nodes.persist import persist
from aggregator.graph.nodes.publish import publish
from aggregator.graph.nodes.rss_collector import rss_collector
from aggregator.graph.nodes.summarize import summarize

__all__ = [
    "rss_collector",
    "deduplicate",
    "summarize",
    "persist",
    "publish",
]