"""The process's connection pool, opened with the application and closed with it."""

from psycopg_pool import AsyncConnectionPool

from app.core.settings import Settings

CONNECT_TIMEOUT_S = 5  # libpq's own wait for one connection; the pool retries on its own


def create_pool(settings: Settings) -> AsyncConnectionPool:
    """A pool that is not open yet; ``await pool.open(wait=False)`` starts it without the database."""
    return AsyncConnectionPool(
        settings.database_url.get_secret_value(),
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        kwargs={"connect_timeout": CONNECT_TIMEOUT_S, "application_name": "kompetenzkartierer-ai"},
        open=False,
        name="kka",
    )
