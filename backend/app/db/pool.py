"""The process's connection pool, opened with the application and closed with it."""

from typing import Any

from psycopg_pool import AsyncConnectionPool

from app.core.settings import Settings

CONNECT_TIMEOUT_S = 5  # libpq's own wait for one connection; the pool retries on its own
# psycopg_pool's default of 300 s, with a backoff that doubles, left a pod unready for minutes
# after the database was back; a chain given up early starts anew at the next request
RECONNECT_TIMEOUT_S = 10
CONNECTION_OPTIONS: dict[str, Any] = {
    "connect_timeout": CONNECT_TIMEOUT_S,
    "application_name": "kompetenzkartierer-ai",
    # A peer gone without a word (stalled network) is noticed within some 30 s, not hours;
    # tcp_user_timeout takes effect where the system has it (Linux)
    "keepalives": 1,
    "keepalives_idle": 10,
    "keepalives_interval": 5,
    "keepalives_count": 3,
    "tcp_user_timeout": 10_000,
}


def create_pool(settings: Settings) -> AsyncConnectionPool:
    """A pool that is not open yet; ``await pool.open(wait=False)`` starts it without the database.

    A connection is checked before it is handed out: after a database restart the pool's
    connections are cut, and each would otherwise fail one request.
    """
    return AsyncConnectionPool(
        settings.database_url.get_secret_value(),
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        kwargs=CONNECTION_OPTIONS,
        check=AsyncConnectionPool.check_connection,
        reconnect_timeout=RECONNECT_TIMEOUT_S,
        open=False,
        name="kka",
    )
