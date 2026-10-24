-- One open job of a key (plan M1 7a): a job may name what it works on as a key - an extraction its
-- document, "extract.run:<id>" - and no two jobs waiting or running share one, so a document is
-- extracted by one job at a time, whoever starts it; once a job has ended, its key is free again.
-- The second index finds a key's latest job, whatever became of it.
ALTER TABLE job
    ADD COLUMN unique_key text CHECK (length(unique_key) BETWEEN 1 AND 200);

CREATE UNIQUE INDEX job_one_open ON job (unique_key)
    WHERE unique_key IS NOT NULL AND status IN ('queued', 'running');
CREATE INDEX job_by_key ON job (unique_key, created_at) WHERE unique_key IS NOT NULL;
