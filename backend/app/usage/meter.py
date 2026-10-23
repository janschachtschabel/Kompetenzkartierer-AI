"""The ledger's meter (plan M1 5.5): what a stage's call reserves and books (app/llm/calls.py,
``ask``) goes to the account's ledger, each on a connection of its own from the pool and in a
transaction of its own - a booking neither waits on the job's work nor is undone with it."""

from psycopg_pool import AsyncConnectionPool

from app.llm.metering import Spent
from app.usage import ledger
from app.usage.ledger import Charge, Reservation


class LedgerMeter:
    """The meter of one job's calls, charged to ``charge``."""

    def __init__(self, pool: AsyncConnectionPool, charge: Charge) -> None:
        self._pool = pool
        self._charge = charge

    async def reserve(self, input_tokens: int, output_tokens: int) -> Reservation:
        async with self._pool.connection() as connection:
            return await ledger.reserve(connection, self._charge, input_tokens, output_tokens)

    async def book(self, reservation: Reservation, spent: Spent) -> None:
        async with self._pool.connection() as connection:
            await ledger.book(connection, reservation, spent)
