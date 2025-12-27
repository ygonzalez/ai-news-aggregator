# AI News Aggregator

A LangGraph-powered pipeline that collects AI/ML news from RSS feeds, summarizes them with Claude, and serves them via a REST API.

## Features

- **RSS Collection**: Fetches articles from 10+ AI/ML blogs and newsletters
- **Smart Deduplication**: Merges duplicate articles from multiple sources
- **AI Summarization**: Uses Claude to generate summaries, key points, and topic classification
- **Vector Embeddings**: OpenAI embeddings for semantic search (stored in pgvector)
- **REST API**: FastAPI endpoints for querying processed news
- **LangGraph Orchestration**: Reliable pipeline with state management

## Architecture

```
START
  │
  ▼
┌─────────────────┐
│  RSS Collector  │  ← Fetches from configured feeds
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Deduplicate   │  ← Merges duplicate articles
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Summarize     │  ← Claude processes each article
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Persist      │  ← Saves to PostgreSQL + pgvector
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Publish      │  ← Formats JSON output
└────────┬────────┘
         │
         ▼
        END
```

## Prerequisites

- Python 3.13+
- Docker (for PostgreSQL)
- [uv](https://docs.astral.sh/uv/) package manager
- Anthropic API key
- OpenAI API key

## Quick Start

### 1. Clone and Install

```bash
cd ai-news-aggregator
uv sync
```

### 2. Configure Environment

Create a `.env` file:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Optional - defaults shown
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/news_aggregator
LOG_LEVEL=INFO

# Optional - LangSmith tracing
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=ai-news-aggregator
```

### 3. Start PostgreSQL

```bash
docker compose up -d
```

This starts PostgreSQL 16 with pgvector on port 5433.

### 4. Initialize Database

```bash
uv run python -m aggregator.main setup-db
```

### 5. Run the Pipeline

```bash
# Collect today's news
uv run python -m aggregator.main run

# Or with 7 days of history
uv run python -m aggregator.main run --backfill 7
```

### 6. Start the API Server

```bash
uv run python -m aggregator.main serve
```

Visit:
- API docs: http://localhost:8000/docs
- News items: http://localhost:8000/items

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/health` | Detailed health status |
| POST | `/run` | Trigger pipeline run |
| GET | `/items` | List news items |
| GET | `/items/{id}` | Get specific item |
| GET | `/topics` | List available topics |

### Query Parameters for `/items`

- `limit` (1-100): Max items to return (default: 20)
- `topic`: Filter by topic (e.g., "LLMs", "AI Safety")
- `min_relevance` (0-1): Minimum relevance score (default: 0)

### Example Response

```json
{
  "items": [
    {
      "id": "abc123",
      "title": "New LLM Breakthrough Announced",
      "summary": "Researchers have developed...",
      "key_points": [
        "50% improvement in reasoning",
        "Lower computational cost",
        "Open source release planned"
      ],
      "topics": ["LLMs", "Research"],
      "relevance_score": 0.92,
      "urls": ["https://example.com/article"],
      "sources": ["rss"],
      "published_at": "2024-12-27T10:00:00Z"
    }
  ],
  "count": 1
}
```

## Configuration

### RSS Feeds

Edit `src/aggregator/config.py` to customize feeds:

```python
DEFAULT_RSS_FEEDS = [
    RssFeedConfig(name="My Blog", url="https://example.com/feed.xml"),
    # Add more feeds...
]
```

### Topic Categories

Items are classified into these categories:
- LLMs
- AI Agents
- AI Safety
- MLOps
- Computer Vision
- NLP
- Open Source
- Products
- Research
- Industry

## Development

### Run Tests

```bash
uv run pytest -v
```

### Project Structure

```
src/aggregator/
├── config.py           # Settings and feed configuration
├── api.py              # FastAPI endpoints
├── main.py             # CLI entry point
├── db/
│   ├── connection.py   # Database pool management
│   └── setup_db.py     # Schema creation
└── graph/
    ├── state.py        # LangGraph state schemas
    ├── orchestrator.py # Pipeline wiring
    └── nodes/
        ├── rss_collector.py
        ├── deduplicate.py
        ├── summarize.py
        ├── persist.py
        └── publish.py
```

### Adding a New Node

1. Create `src/aggregator/graph/nodes/my_node.py`
2. Define an async function that takes `AggregatorState` and returns a dict
3. Add the node in `orchestrator.py`:
   ```python
   builder.add_node("my_node", my_node)
   builder.add_edge("previous_node", "my_node")
   ```

## License

MIT