-- The source register (plan M1, package 1): what a curriculum document is, where it came from,
-- whose it is and on what terms it may be used (app/sources/register.py names the same lists).
-- Who may see an entry is decided at source, never at source_file: one file is shared across
-- accounts by its SHA-256.

-- A value of a fixed scheme points at (scheme, iri): it cannot name a concept of another
-- scheme. Comes with the first domain table (plan M0).
ALTER TABLE vocab_concept ADD CONSTRAINT vocab_concept_in_scheme UNIQUE (scheme_iri, iri);

-- A file as the store holds it, under sources/<sha256>; the same bytes are one row. Its type is
-- the entry's: text has no signature and is known by the name it came by
CREATE TABLE source_file (
    id uuid PRIMARY KEY,
    sha256 bytea NOT NULL UNIQUE CHECK (length(sha256) = 32),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    storage_key text NOT NULL UNIQUE CHECK (length(storage_key) BETWEEN 1 AND 512),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'source' CHECK (kind = 'source'),
    -- the account whose entry it is; none for a seed or research entry, whose metadata all see
    owner_id uuid REFERENCES account (id),
    provenance text NOT NULL CHECK (provenance IN (
        'upload', 'url', 'vergleichsdatensatz-v62.493', 'laenderrecherche', 'ttl', 'recherche', 'redaktion'
    )),
    title text NOT NULL DEFAULT '' CHECK (length(title) <= 500),
    url text CHECK (url ~ '^https?://' AND length(url) <= 2000),
    country text CHECK (country ~ '^[A-Z]{2}(-[A-Z0-9]{1,3})?$'),  -- ISO 3166-1 or -2: DE, DE-BY
    sector_scheme text CHECK (sector_scheme = 'https://w3id.org/wlo/curriculum/vocab#EducationSectors'),
    sector_iri text,
    rights_status text NOT NULL DEFAULT 'unklar'
        CHECK (rights_status IN ('amtlich', 'offen_lizenziert', 'geschuetzt', 'unklar')),
    rights_evidence text CHECK (length(rights_evidence) <= 2000),
    license text CHECK (length(license) <= 200),
    source_type text CHECK (source_type IN ('amtlich', 'archiv', 'spiegel', 'sekundaer')),
    register_status text NOT NULL DEFAULT 'unchecked'
        CHECK (register_status IN ('unchecked', 'reachable', 'unreachable', 'acquired')),
    file_id uuid REFERENCES source_file (id),
    file_name text CHECK (length(file_name) BETWEEN 1 AND 255),  -- as the stored file is named
    mime text CHECK (mime ~ '^[a-z]+/[a-z0-9.+-]+$'),  -- what the file is, by its bytes and name
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (sector_scheme, sector_iri) REFERENCES vocab_concept (scheme_iri, iri),
    CHECK ((sector_scheme IS NULL) = (sector_iri IS NULL)),
    CHECK ((register_status = 'acquired') = (file_id IS NOT NULL)),
    CHECK ((file_id IS NULL) = (file_name IS NULL)),
    CHECK ((file_id IS NULL) = (mime IS NULL))
);
CREATE INDEX source_owner ON source (owner_id);
CREATE INDEX source_file_ref ON source (file_id);
-- No B-tree on url: 2000 signs may be 8000 bytes, past what one index entry holds (2704)

-- Each time a source's file came in: by upload or by fetching its URL (the chain of addresses
-- fetched, redirects in order)
CREATE TABLE acquisition (
    id uuid PRIMARY KEY,
    source_id uuid NOT NULL REFERENCES source (id),
    file_id uuid NOT NULL REFERENCES source_file (id),
    method text NOT NULL CHECK (method IN ('upload', 'url')),
    account_id uuid REFERENCES account (id),
    chain jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(chain) = 'array'),
    received_name text CHECK (length(received_name) <= 255),  -- as the sender named it
    acquired_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX acquisition_source ON acquisition (source_id, acquired_at);
