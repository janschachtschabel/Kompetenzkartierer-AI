"""The ledger's meter (plan M1 5.5): what a stage's call reserves and books (app/llm/calls.py,
``ask``) goes to the account's ledger, each on a connection of its own from the pool and in a
transaction of its own - a booking neither waits on the job's work nor is undone with it.

With the attempt's ``job``, each reservation first looks at its lease (app/jobs/queue.py,
``check_lease``): a request of an attempt whose job ended - cancelled, its lease lost, its
handler left to unwind - is neither reserved nor sent; LeaseLost instead. Each request of a
call is reserved, its retries too."""

from psycopg_pool import AsyncConnectionPool

from app.jobs.queue import Job, check_lease
from app.llm.metering import Spent
from app.usage import ledger
from app.usage.ledger import Charge, Reservation


class LedgerMeter:
    """The meter of one job's calls, charged to ``charge``; with ``job``, only while its lease holds."""

    def __init__(self, pool: AsyncConnectionPool, charge: Charge, job: Job | None = None) -> None:
        self._pool = pool
        self._charge = charge
        self._job = job

    async def reserve(self, input_tokens: int, output_tokens: int) -> Reservation:
        if self._job is not None:  # on a connection of its own: a reservation is a transaction alone
            async with self._pool.connection() as connection:
                await check_lease(connection, self._job)
        async with self._pool.connection() as connection:
            return await ledger.reserve(connection, self._charge, input_tokens, output_tokens)

    async def book(self, reservation: Reservation, spent: Spent) -> None:
        async with self._pool.connection() as connection:
            await ledger.book(connection, reservation, spent)
