-- How a stage's run ended (plan M1 6.6; app/db/runs.py): the attempt of the job it ran in, its
-- outcome - done, failed, or stopped where the account's budget held no further request - and
-- what it made, as the stage after it reads it (X2's work packages). A run without an outcome
-- has not ended: still running, or cancelled with its job's attempt; the job's next attempt
-- starts a run of its own, and a stage counts as done once one of its runs is.
ALTER TABLE extraction_run
    ADD COLUMN attempt integer CHECK (attempt >= 1),
    ADD COLUMN outcome text CHECK (outcome IN ('done', 'failed', 'budget_exhausted')),
    ADD COLUMN result jsonb CHECK (jsonb_typeof(result) = 'object'),
    ADD CONSTRAINT extraction_run_ends_with_its_outcome CHECK ((finished_at IS NULL) = (outcome IS NULL));
