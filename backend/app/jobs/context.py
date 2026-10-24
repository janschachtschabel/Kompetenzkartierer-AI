"""What a job handler works with: the database pool, the object store, the settings - and, for
a job that asks the language model, the model layer's settings and the process's model.

The worker builds one context at its start and hands it to ``make_handlers``
(app/jobs/handlers.py), which binds every handler to it; no handler reaches for a module-level
pool or store, so a test gives it its own.
"""

from collections.abc import Callable
from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool
from pydantic_ai.models import Model

from app.core.settings import Settings
from app.core.storage_async import AsyncStorage
from app.llm.settings import LLMSettings


@dataclass(frozen=True)
class JobContext:
    pool: AsyncConnectionPool
    storage: AsyncStorage
    settings: Settings
    llm: LLMSettings | None = None
    # built when a job first asks for it, once a process (app/llm/client.py, LazyModel)
    model: Callable[[], Model] | None = None
