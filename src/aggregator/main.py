"""
Main entry point for the AI News Aggregator.

This module provides multiple ways to run the application:

1. API Server Mode (default):
   python -m aggregator.main
   python -m aggregator.main serve

2. Pipeline Run Mode (one-shot):
   python -m aggregator.main run
   python -m aggregator.main run --backfill 7

3. Database Setup Mode:
   python -m aggregator.main setup-db

Usage Examples:
    # Start the API server
    python -m aggregator.main serve --port 8000

    # Run the pipeline once
    python -m aggregator.main run --backfill 7

    # Set up the database
    python -m aggregator.main setup-db

How This Works:
- The CLI uses argparse for argument parsing
- Each command (serve, run, setup-db) maps to an async function
- asyncio.run() is used to run the async functions
- structlog provides structured logging throughout
"""

# Load .env into os.environ BEFORE importing LangChain modules
# This ensures LangSmith tracing is configured correctly
from dotenv import load_dotenv

load_dotenv()

import argparse
import asyncio
import sys

import structlog
import uvicorn

from aggregator.config import get_settings

# ========================================
# LOGGING CONFIGURATION
# structlog provides structured, context-aware logging
# ========================================

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),  # Pretty console output for development
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


# ========================================
# COMMAND FUNCTIONS
# Each command runs in its own async context
# ========================================


async def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """
    Start the FastAPI server.

    Uses uvicorn as the ASGI server. The API endpoints are defined
    in aggregator/api.py.

    Args:
        host: Host to bind to (0.0.0.0 for all interfaces)
        port: Port to listen on
        reload: Enable auto-reload on code changes (development only)
    """
    logger.info("Starting API server", host=host, port=port, reload=reload)

    config = uvicorn.Config(
        "aggregator.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_pipeline(backfill_days: int = 0):
    """
    Run the pipeline once and exit.

    This is useful for:
    - Initial data population
    - Scheduled cron jobs
    - Manual data refresh

    Args:
        backfill_days: Days of historical data to collect
    """
    from aggregator.db import close_db_pool
    from aggregator.graph import run_aggregator

    logger.info("Running pipeline", backfill_days=backfill_days)

    try:
        result = await run_aggregator(backfill_days=backfill_days)

        stats = result.get("stats", {})
        logger.info(
            "Pipeline completed",
            items_processed=stats.get("total_items", 0),
            items_persisted=stats.get("persisted_count", 0),
            errors=stats.get("collection_errors", 0),
        )

        # Print summary to console
        print("\n" + "=" * 60)
        print("Pipeline Run Complete")
        print("=" * 60)
        print(f"Items processed: {stats.get('total_items', 0)}")
        print(f"Items persisted: {stats.get('persisted_count', 0)}")
        print(f"Collection errors: {stats.get('collection_errors', 0)}")

        # Show top items if available
        items = result.get("items", [])
        if items:
            print(f"\nTop {min(5, len(items))} items:")
            for item in items[:5]:
                title = item.get("title", "No title")
                if len(title) > 60:
                    title = title[:57] + "..."
                print(f"  - {title}")

    except Exception as e:
        logger.error("Pipeline failed", error=str(e))
        print(f"\nPipeline failed: {e}")
        sys.exit(1)

    finally:
        await close_db_pool()


async def setup_database():
    """
    Set up the database schema.

    Creates:
    - news_items table with pgvector support
    - pipeline_runs table for tracking
    - Required indexes
    """
    from aggregator.db import close_db_pool
    from aggregator.db.setup_db import get_table_stats, setup_database

    logger.info("Setting up database")

    try:
        await setup_database()
        stats = await get_table_stats()

        print("\n" + "=" * 60)
        print("Database Setup Complete")
        print("=" * 60)
        print(f"news_items: {stats['news_items']} rows")
        print(f"pipeline_runs: {stats['pipeline_runs']} rows")
        print("\nDatabase is ready for use!")

    except Exception as e:
        logger.error("Database setup failed", error=str(e))
        print(f"\nDatabase setup failed: {e}")
        print("\nMake sure PostgreSQL is running and the connection string is correct.")
        sys.exit(1)

    finally:
        await close_db_pool()


# ========================================
# CLI ENTRY POINT
# ========================================


def main():
    """
    Main entry point with CLI argument parsing.

    Supports three commands:
    - serve: Start the API server
    - run: Run the pipeline once
    - setup-db: Initialize the database
    """
    parser = argparse.ArgumentParser(
        description="AI News Aggregator - Collect and summarize AI/ML news",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m aggregator.main serve             # Start API server
  python -m aggregator.main serve --port 8080 # Custom port
  python -m aggregator.main run               # Run pipeline once
  python -m aggregator.main run --backfill 7  # With 7 days of history
  python -m aggregator.main setup-db          # Initialize database
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ========================================
    # serve command
    # ========================================
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    # ========================================
    # run command
    # ========================================
    run_parser = subparsers.add_parser("run", help="Run the pipeline once")
    run_parser.add_argument(
        "--backfill",
        type=int,
        default=0,
        help="Days of historical data to collect (default: 0 = today only)",
    )

    # ========================================
    # setup-db command
    # ========================================
    subparsers.add_parser("setup-db", help="Initialize the database schema")

    args = parser.parse_args()

    # Default to 'serve' if no command specified
    if args.command is None:
        args.command = "serve"
        args.host = "0.0.0.0"
        args.port = 8000
        args.reload = False

    # ========================================
    # Validate settings early
    # This catches configuration errors before starting
    # ========================================
    try:
        settings = get_settings()
        logger.debug(
            "Settings loaded",
            log_level=settings.log_level,
            langsmith_enabled=settings.langsmith_tracing,
        )
    except Exception as e:
        logger.error("Failed to load settings", error=str(e))
        print(f"\nConfiguration Error: {e}")
        print("\nMake sure you have a .env file with required settings.")
        print("Required variables: ANTHROPIC_API_KEY, OPENAI_API_KEY")
        print("\nSee .env.example for a template.")
        sys.exit(1)

    # ========================================
    # Run the appropriate command
    # ========================================
    if args.command == "serve":
        asyncio.run(run_server(host=args.host, port=args.port, reload=args.reload))
    elif args.command == "run":
        asyncio.run(run_pipeline(backfill_days=args.backfill))
    elif args.command == "setup-db":
        asyncio.run(setup_database())


if __name__ == "__main__":
    main()
