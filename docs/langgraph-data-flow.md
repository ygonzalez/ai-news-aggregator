# LangGraph Data Flow

This document explains how data flows through the AI News Aggregator pipeline, including the state schema, nodes, and orchestration.

## Pipeline Overview

```
┌─────────┐    ┌──────────────┐    ┌─────────────┐    ┌───────────┐    ┌─────────┐    ┌─────────┐
│  START  │───▶│ RSS Collector│───▶│ Deduplicate │───▶│ Summarize │───▶│ Persist │───▶│ Publish │───▶ END
└─────────┘    └──────────────┘    └─────────────┘    └───────────┘    └─────────┘    └─────────┘
     │                │                   │                 │               │              │
     │           raw_items           deduplicated      processed       persisted      publication
     │        collection_errors         _items           _items          _count         _payload
     │                │                   │                 │               │              │
     ▼                ▼                   ▼                 ▼               ▼              ▼
  run_id         RawItem[]           RawItem[]       ProcessedItem[]      int            dict
  run_date
  backfill_days
```

---

## State Schema

The pipeline uses a single `AggregatorState` TypedDict that flows through all nodes. Each node reads what it needs and returns partial updates.

**File:** `src/aggregator/graph/state.py`

### AggregatorState Fields

| Field | Type | Set By | Description |
|-------|------|--------|-------------|
| `run_id` | `str` | START | Unique identifier for this pipeline run |
| `run_date` | `datetime` | START | When the pipeline was triggered |
| `backfill_days` | `int` | START | How many days of history to collect |
| `raw_items` | `list[RawItem]` | Collectors | Articles fetched from sources |
| `collection_errors` | `list[CollectionError]` | Collectors | Non-fatal errors during collection |
| `deduplicated_items` | `list[RawItem]` | Deduplicate | Items after removing duplicates |
| `processed_items` | `list[ProcessedItem]` | Summarize | Items after Claude processing |
| `persisted_count` | `int` | Persist | Number of items saved to database |
| `publication_payload` | `dict` | Publish | Final JSON output |

### Key Design Patterns

1. **`total=False`** - All fields are optional. Nodes return partial updates, not the full state.

2. **Annotated Reducers** - For parallel node outputs:
   ```python
   raw_items: Annotated[list[RawItem], operator.add]
   ```
   This tells LangGraph to concatenate lists from parallel nodes instead of overwriting.

---

## Data Types

### RawItem

Raw article as collected from RSS/Gmail before any processing.

```python
class RawItem(TypedDict):
    source_type: Literal["rss", "gmail"]  # Where it came from
    source_id: str                         # Feed URL or sender email
    item_id: str                           # SHA256 hash of URL (for dedup)
    title: str | None                      # May be missing in some emails
    content: str                           # Main text content
    author: str | None
    published_at: datetime
    url: str | None
    raw_metadata: dict                     # Source-specific data
```

### ProcessedItem

Article after Claude summarization, ready for storage.

```python
class ProcessedItem(TypedDict):
    item_id: str
    title: str                    # LLM may generate if missing
    summary: str                  # 2-3 paragraph summary
    key_points: list[str]         # 3-5 bullet points
    topics: list[str]             # From predefined categories
    article_type: str             # "news" or "tutorial"
    original_urls: list[str]      # May have multiple if merged
    source_types: list[str]       # ["rss"], ["gmail"], or both
    published_at: datetime
    processed_at: datetime
    embedding: list[float] | None # 1536-dim vector for similarity
```

### CollectionError

Non-fatal error during collection (logged but doesn't stop pipeline).

```python
class CollectionError(TypedDict):
    source_type: Literal["rss", "gmail"]
    source_id: str
    error_type: str
    error_message: str
    timestamp: datetime
```

---

## Node Details

### 1. RSS Collector

**File:** `src/aggregator/graph/nodes/rss_collector.py`

**Purpose:** Fetch and parse RSS/Atom feeds from configured sources.

**Input:**
- `state.run_date` - Current timestamp
- `state.backfill_days` - How far back to collect

**Output:**
```python
{
    "raw_items": [...],        # List of RawItem
    "collection_errors": [...] # List of CollectionError
}
```

**How it works:**
1. Reads feeds from `DEFAULT_RSS_FEEDS` in config
2. Fetches all feeds concurrently using `httpx.AsyncClient`
3. Parses XML with `feedparser`
4. Filters items older than `cutoff_date = run_date - backfill_days`
5. Generates `item_id` by hashing the URL
6. Converts entries to `RawItem` format
7. Captures errors without failing the pipeline

**Key functions:**
- `fetch_single_feed()` - Fetches and parses one feed
- `generate_item_id()` - Creates unique ID from URL hash
- `parse_published_date()` - Handles various date formats
- `extract_content()` - Gets best content from entry fields

---

### 2. Deduplicate

**File:** `src/aggregator/graph/nodes/deduplicate.py`

**Purpose:** Remove duplicate articles that appear in multiple sources.

**Input:**
- `state.raw_items` - All items from collectors

**Output:**
```python
{
    "deduplicated_items": [...]  # List of RawItem (merged)
}
```

**How it works:**
1. Groups items by `item_id` (same URL = same hash)
2. Merges duplicates:
   - Keeps longest content
   - Uses earliest `published_at`
   - Preserves all source references
   - Merges metadata
3. Sorts by date (newest first)

**Merging example:**
```python
# Same article from RSS and Gmail becomes:
{
    "source_type": "rss",  # Primary source
    "raw_metadata": {
        "merged_from_sources": ["rss", "gmail"],
        "merged_from_ids": ["feed_url", "sender@email.com"],
        "all_urls": ["https://article.com"],
    }
}
```

---

### 3. Summarize

**File:** `src/aggregator/graph/nodes/summarize.py`

**Purpose:** Use Claude to generate summaries, key points, and classifications.

**Input:**
- `state.deduplicated_items` - Items to process

**Output:**
```python
{
    "processed_items": [...]  # List of ProcessedItem
}
```

**How it works:**
1. Initializes Claude (`claude-sonnet-4-20250514`) with structured output
2. Optionally initializes OpenAI embeddings (`text-embedding-3-small`)
3. Processes items concurrently with semaphore (default 5 concurrent)
4. For each item:
   - Formats prompt with article content
   - Calls Claude with `ArticleSummary` schema
   - Retries up to 2 times on validation errors
   - Generates embedding if enabled
   - Creates `ProcessedItem`

**Structured Output Schema:**
```python
class ArticleSummary(BaseModel):
    title: str
    summary: str                    # 2-3 paragraphs
    key_points: list[str]           # 3-5 items
    topics: list[str]               # From TOPIC_CATEGORIES
    article_type: str               # "news" or "tutorial"
```

**Topic Categories:**
- LLMs, AI Agents, AI Safety, MLOps
- Computer Vision, NLP, Open Source
- Products, Research, Industry

---

### 4. Persist

**File:** `src/aggregator/graph/nodes/persist.py`

**Purpose:** Save processed items to PostgreSQL using upsert.

**Input:**
- `state.processed_items` - Items to save
- `state.run_id` - For pipeline_runs tracking

**Output:**
```python
{
    "persisted_count": 42  # Number successfully saved
}
```

**How it works:**
1. Gets database connection from pool
2. Creates/updates `pipeline_runs` record with status "running"
3. For each item:
   - Converts lists to JSON for JSONB columns
   - Executes upsert SQL (INSERT ... ON CONFLICT UPDATE)
   - Uses savepoints so individual failures don't abort transaction
4. Updates `pipeline_runs` with final count and "completed" status

**Why Upsert?**
- Running pipeline twice on same day won't cause duplicate key errors
- Existing records get updated with latest processing
- `published_at` and `created_at` are preserved on update

---

### 5. Publish

**File:** `src/aggregator/graph/nodes/publish.py`

**Purpose:** Format the final output payload for API consumption.

**Input:**
- `state.processed_items` - All processed items
- `state.persisted_count` - Database save count
- `state.collection_errors` - Errors to include

**Output:**
```python
{
    "publication_payload": {
        "meta": {
            "run_id": "run_20240115_143022_abc123",
            "run_date": "2024-01-15T14:30:22Z",
            "generated_at": "2024-01-15T14:35:00Z",
            "version": "1.0"
        },
        "stats": {
            "total_items": 42,
            "persisted_count": 42,
            "collection_errors": 2,
            "topic_distribution": {"LLMs": 15, "AI Agents": 10, ...},
            "source_distribution": {"rss": 40, "gmail": 2},
            "article_type_distribution": {"news": 35, "tutorial": 7}
        },
        "by_topic": {
            "LLMs": [{...}, {...}],
            "AI Agents": [{...}]
        },
        "items": [{...}, {...}, ...],
        "errors": [{...}, {...}]
    }
}
```

**How it works:**
1. Formats each item for API (converts datetimes to ISO strings, removes embeddings)
2. Groups items by primary topic
3. Generates summary statistics
4. Builds final payload structure

---

## Orchestrator

**File:** `src/aggregator/graph/orchestrator.py`

**Purpose:** Wire nodes together into a LangGraph and execute.

### Graph Construction

```python
# 1. Create graph with state schema
builder = StateGraph(AggregatorState)

# 2. Add nodes
builder.add_node("rss_collector", rss_collector)
builder.add_node("deduplicate", deduplicate)
builder.add_node("summarize", summarize)
builder.add_node("persist", persist)
builder.add_node("publish", publish)

# 3. Add edges (execution order)
builder.add_edge(START, "rss_collector")
builder.add_edge("rss_collector", "deduplicate")
builder.add_edge("deduplicate", "summarize")
builder.add_edge("summarize", "persist")
builder.add_edge("persist", "publish")
builder.add_edge("publish", END)

# 4. Compile
graph = builder.compile()
```

### Execution

```python
# Initial state
initial_state = {
    "run_id": "run_20240115_143022_abc123",
    "run_date": datetime.now(UTC),
    "backfill_days": 7,
}

# Execute graph
final_state = await graph.ainvoke(initial_state)

# Get results
payload = final_state["publication_payload"]
```

### Caching

The compiled graph is cached in `_cached_graph` since compilation is expensive:

```python
def get_graph() -> StateGraph:
    global _cached_graph
    if _cached_graph is None:
        _cached_graph = create_graph()
    return _cached_graph
```

---

## Full Data Flow Example

```
1. START
   State: {run_id: "run_123", run_date: "2024-01-15", backfill_days: 7}

2. RSS Collector
   Reads: run_date, backfill_days
   Fetches 50 articles from 10 feeds (concurrent)
   Returns: {raw_items: [50 RawItems], collection_errors: [2 errors]}

3. Deduplicate
   Reads: raw_items (50 items)
   Finds 5 duplicates (same article in multiple feeds)
   Returns: {deduplicated_items: [45 RawItems]}

4. Summarize
   Reads: deduplicated_items (45 items)
   Calls Claude 45 times (5 concurrent)
   3 items fail validation
   Returns: {processed_items: [42 ProcessedItems]}

5. Persist
   Reads: processed_items, run_id
   Upserts to PostgreSQL
   Returns: {persisted_count: 42}

6. Publish
   Reads: processed_items, persisted_count, collection_errors
   Formats final payload
   Returns: {publication_payload: {...}}

7. END
   Final state has all fields populated
   publication_payload returned to caller
```

---

## Error Handling

The pipeline uses **graceful degradation**:

1. **Collection errors** - Logged but don't stop pipeline. Partial results are better than no results.

2. **Summarization failures** - Individual items can fail (retries exhausted). Others continue.

3. **Persistence failures** - Uses savepoints per item. One failure doesn't abort the transaction.

4. **All errors tracked** - `collection_errors` included in final payload for debugging.
