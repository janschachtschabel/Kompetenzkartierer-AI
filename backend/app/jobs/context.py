"""What a job handler works with: the database pool, the object store and the settings.

The worker builds one context at its start and hands it to ``make_handlers``
(app/jobs/handlers.py), which binds every handler to it; no handler reaches for a module-level
pool or store, so a test gives it its own.
"""

from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool

from app.core.settings import Settings
from app.core.storage_async import AsyncStorage


@dataclass(frozen=True)
class JobContext:
    pool: AsyncConnectionPool
    storage: AsyncStorage
    settings: Settings
