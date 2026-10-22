-- The job queue: the table is the truth (app/jobs/queue.py). Workers claim with
-- FOR UPDATE SKIP LOCKED, hold a lease they renew, and only the lease's owner may finish a
-- job. Times are the database's, so the clocks of the pods do not matter.
CREATE TABLE job (
    id uuid PRIMARY KEY,
    kind text NOT NULL CHECK (kind ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'),
    -- whose turn it is: an account's id, or "system"; one busy account does not hold back others
    lane text NOT NULL CHECK (length(lane) BETWEEN 1 AND 100),
    payload jsonb NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    run_after timestamptz NOT NULL DEFAULT now(),
    lease_owner text,
    lease_expires_at timestamptz,
    cancel_requested boolean NOT NULL DEFAULT false,
    result jsonb,
    error jsonb,  -- {code, message}: no traceback, it may hold input
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    -- a running job has its lease, no other has one
    CHECK ((status = 'running') = (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL))
);

CREATE INDEX job_waiting ON job (created_at) WHERE status = 'queued';
CREATE INDEX job_running ON job (lane, lease_expires_at) WHERE status = 'running';
