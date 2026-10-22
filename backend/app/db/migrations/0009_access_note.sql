-- How a land's documents can be reached where its portal blocks or moved them (plan M1, 2.3;
-- Gesamtplan §7.5): the comparison dataset's notes on blocked portals and detours, each for a
-- land, school form and subject. A register entry seeded with the same three shows them; a note
-- without a school form or subject holds for all of them in its land. The
-- rule stays ours: official sources first, an archive as one, a mirror marked; a technical
-- barrier is never got round. A note's key is the SHA-256 of its row: a second import adds nothing.
CREATE TABLE access_note (
    id uuid PRIMARY KEY,
    dataset text NOT NULL CHECK (dataset IN ('vergleichsdatensatz-v62.493')),
    note_key text NOT NULL CHECK (note_key ~ '^[0-9a-f]{64}$'),
    country text CHECK (country ~ '^[A-Z]{2}(-[A-Z0-9]{1,3})?$'),
    school_form text CHECK (length(school_form) BETWEEN 1 AND 200),
    subject text CHECK (length(subject) BETWEEN 1 AND 200),
    categories text[] NOT NULL DEFAULT '{}',
    field text CHECK (length(field) BETWEEN 1 AND 200),
    text text NOT NULL CHECK (length(text) BETWEEN 1 AND 4000),
    url text CHECK (url ~ '^https?://' AND length(url) <= 2000),
    origin text CHECK (length(origin) BETWEEN 1 AND 200),
    UNIQUE (dataset, note_key)
);
CREATE INDEX access_note_scope ON access_note (country, school_form, subject);
