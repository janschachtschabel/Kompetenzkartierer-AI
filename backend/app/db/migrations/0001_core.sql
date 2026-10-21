-- The core: the extensions the plan relies on and the one id space all addressable things share.
--
-- Creating an extension needs the right to do so (owner of the database with trusted
-- extensions, or a superuser). Where the migration role lacks it, the operator creates the
-- three beforehand; IF NOT EXISTS then leaves them alone.
CREATE EXTENSION IF NOT EXISTS vector;    -- embeddings, halfvec and HNSW (pgvector)
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- similarity search on labels and titles
CREATE EXTENSION IF NOT EXISTS unaccent;  -- accent-folded full-text search

-- Every document, node, statement and concept gets its id here; value objects, anchors and
-- edges point at entity.id, so a reference to any subject stays checked by a foreign key
-- without polymorphic columns. Ids are UUIDv7, made by the application (PostgreSQL 17 has no
-- uuidv7()). A typed table fixes its kind and points at (id, kind), so a node's id cannot
-- belong to a statement.
CREATE TABLE entity (
    id uuid PRIMARY KEY,
    kind text NOT NULL CHECK (kind ~ '^[a-z][a-z_]*$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, kind)
);
