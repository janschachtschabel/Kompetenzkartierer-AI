-- The vocabularies of Curriculum-Kern 1.0, loaded from the ontology's Turtle files by
-- python -m app.vocab.load. Required values of the domain tables (statement kind, addressee,
-- edge kind, ...) point at vocab_concept.iri, so a new value needs a line of Turtle, not a
-- migration. A scheme or concept the files no longer hold is retired, not deleted: rows may
-- still point at it.

-- One row per loaded content; a load of the same files as the latest release adds none
CREATE TABLE vocab_release (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    files jsonb NOT NULL,  -- {path under ontology/: SHA-256}
    loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE vocab_scheme (
    iri text PRIMARY KEY,
    types text[] NOT NULL,
    pref_labels jsonb NOT NULL,  -- {language: label}
    properties jsonb NOT NULL,   -- every other statement: {predicate: [{iri} | {value, lang | datatype}]}
    retired_in integer REFERENCES vocab_release (id)
);

CREATE TABLE vocab_concept (
    iri text PRIMARY KEY,
    scheme_iri text NOT NULL REFERENCES vocab_scheme (iri),
    types text[] NOT NULL,
    notation text,
    pref_labels jsonb NOT NULL,  -- {language: label}
    alt_labels jsonb NOT NULL,   -- {language: [labels]}
    definitions jsonb NOT NULL,  -- {language: text}
    broader text[] NOT NULL,     -- concepts of these tables; the loader checks they exist
    properties jsonb NOT NULL,
    retired_in integer REFERENCES vocab_release (id)
);

CREATE INDEX vocab_concept_scheme ON vocab_concept (scheme_iri);
