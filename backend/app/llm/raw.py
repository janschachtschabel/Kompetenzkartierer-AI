"""A run's model answers kept as they came, before anything reads them (plan M1 5.3): the evidence
of what a stage was told, and of what it cost - each answer carries its usage.

Kept in the object store under ``runs/<run-id>/<stage>/<n>.json``, numbered from 1 in the order
the answers came. The store cannot list, so each number is the next one free after the last this
keeper took: a job asked again after a crash goes on behind what its run kept, and writes over
nothing, gaps and all. That holds for one keeper of a run and stage at a time: two side by side
could take one number, so a run is one attempt of a job (plan M1, Nachtrag 5.3). Written off the
event loop, as the store is synchronous.
"""

import asyncio
import re
from uuid import UUID

from app.core.storage import Storage

# a stage as the core names them, lowercase: x0 to x6, n1, g1
_STAGE = re.compile(r"[a-z][a-z0-9]{0,15}")


class RawResponses:
    """The keeper of one run's answers at one stage (``x4``)."""

    def __init__(self, storage: Storage, run_id: UUID, stage: str) -> None:
        if _STAGE.fullmatch(stage) is None:
            raise ValueError(f"{stage!r} is no stage's name, as x4 is")
        self._storage = storage
        self._prefix = f"runs/{run_id}/{stage}"
        self._next = 1
        self._taking = asyncio.Lock()

    async def keep(self, data: bytes) -> str:
        """Keep ``data`` under the next free number; its key."""
        async with self._taking:
            key = await asyncio.to_thread(self._free_key)
        await asyncio.to_thread(self._storage.put, key, data)
        return key

    def _free_key(self) -> str:
        while self._storage.exists(key := f"{self._prefix}/{self._next}.json"):
            self._next += 1
        self._next += 1
        return key
