-- The job queue: the table is the truth (app/jobs/queue.py). Workers claim with
-- FOR UPDATE SKIP LOCKED, hold a lease they renew, and only the claim that holds the lease may
-- finish a job. Times are the database's, so the clocks of the pods do not matter.

-- Every lane that has had a job, and when a claim last took one of its jobs: lanes take turns
CREATE TABLE job_lane (
    lane text PRIMARY KEY,
    served_at timestamptz
);

CREATE TABLE job (
    id uuid PRIMARY KEY,
    kind text NOT NULL CHECK (kind ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'),
    -- whose turn it is: an account's id, or "system"; one busy account does not hold back others
    lane text NOT NULL REFERENCES job_lane (lane) CHECK (length(lane) BETWEEN 1 AND 100),
    payload jsonb NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 100),
    run_after timestamptz NOT NULL DEFAULT now(),
    lease_owner text,  -- the worker, for people reading the table
    lease_token uuid,  -- the claim: a restarted worker may get its old name again
    lease_expires_at timestamptz,
    cancel_requested boolean NOT NULL DEFAULT false,
    result jsonb,
    error jsonb,  -- {code, message}: no traceback, it may hold input
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    -- a running job has its lease, no other has one
    CHECK ((status = 'running') = (
        lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL
    ))
);

-- a lane's next waiting job, without sorting the whole queue
CREATE INDEX job_waiting ON job (lane, created_at) WHERE status = 'queued';
CREATE INDEX job_running ON job (lane, lease_expires_at) WHERE status = 'running';
