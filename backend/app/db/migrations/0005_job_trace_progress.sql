-- What a running job reports, and the trace of the request that made it (app/jobs/queue.py).
-- progress is {code, params}, written only under the job's lease; the worker writes the job's
-- log lines with trace_id, so a request's lines and those of its jobs are found together. The
-- trace id is caller input: the signs and length app/core/tracing.py lets through.
ALTER TABLE job ADD COLUMN progress jsonb;
-- (the length apart: PostgreSQL's regular expressions repeat at most 255 times)
ALTER TABLE job ADD COLUMN trace_id text
    CHECK (length(trace_id) BETWEEN 1 AND 256 AND trace_id ~ '^[A-Za-z0-9._:@+/=,-]+$');
