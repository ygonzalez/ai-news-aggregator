"""Database module for the news aggregator."""

from aggregator.db.connection import close_db_pool, get_db_pool

__all__ = ["get_db_pool", "close_db_pool"]
