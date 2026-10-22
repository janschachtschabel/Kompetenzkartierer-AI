-- What a seed dataset or a land's research said of a register entry, beside what the register
-- asserts itself (plan M1, 2.2 and 2.4; Gesamtplan §7.5): the published fields of a candidate,
-- kept apart so the register's own columns stay the register's. One row per entry; a dataset's
-- row key makes a second import change nothing.
CREATE TABLE source_seed (
    source_id uuid PRIMARY KEY REFERENCES source (id),
    dataset text NOT NULL CHECK (dataset IN ('vergleichsdatensatz-v62.493', 'laenderrecherche')),
    seed_key text NOT NULL CHECK (length(seed_key) BETWEEN 1 AND 200),
    school_form text CHECK (length(school_form) BETWEEN 1 AND 200),
    stage text CHECK (length(stage) BETWEEN 1 AND 200),
    subject_key text CHECK (length(subject_key) BETWEEN 1 AND 100),
    subject text CHECK (length(subject) BETWEEN 1 AND 200),
    grade_from smallint CHECK (grade_from BETWEEN 0 AND 13),
    grade_to smallint CHECK (grade_to BETWEEN 0 AND 13),
    binding text CHECK (length(binding) BETWEEN 1 AND 500),
    archive_url text CHECK (archive_url ~ '^https?://' AND length(archive_url) <= 2000),
    archived_at text CHECK (length(archived_at) BETWEEN 1 AND 40),
    -- of a research row: found in the primary document (E) or only in a secondary one (S)
    evidence text CHECK (evidence IN ('E', 'S')),
    UNIQUE (dataset, seed_key),
    CHECK (grade_from IS NULL OR grade_to IS NULL OR grade_from <= grade_to)
);
