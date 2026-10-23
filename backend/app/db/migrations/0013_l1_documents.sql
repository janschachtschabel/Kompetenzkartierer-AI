-- The first layer's frame (plan M1 4.2, konzept §5, §11): the work a document is a version of,
-- the document - one edition of a source, as converted - and what it stands for: its
-- specifications and their variants; and the runs of the pipeline's stages on a document. What
-- X1 has yet to find (title, document type, legal form, dates) may be missing here: the core's
-- shapes (cur-shapes.ttl) check a document whole in X5. Who may see a document is decided here,
-- at document, never at what it was converted from (app/db/documents.py).

-- Text that is more than space: what Python's str.strip() leaves of it is not empty - its 29
-- signs of space written out, as in 0006, since [[:space:]] follows the locale. NULL stays NULL,
-- so a CHECK on a column that may be empty passes on it
CREATE FUNCTION has_text(value text) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    RETURN btrim(value, U&'!0009!000A!000B!000C!000D!001C!001D!001E!001F!0020!0085!00A0!1680!2000!2001!2002!2003!2004!2005!2006!2007!2008!2009!200A!2028!2029!202F!205F!3000' UESCAPE '!') <> '';

-- Every item of an array matches the pattern, and none is NULL
CREATE FUNCTION all_match(items text[], pattern text) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    RETURN NOT EXISTS (SELECT FROM unnest(items) AS item WHERE item IS NULL OR item !~ pattern);

-- A work: what stays the same over a document's editions. The editors set it (plan M1 9.6); its
-- IRI, …/work/<country>/<short title>, comes when a document of it is frozen (app/domain/iris.py)
CREATE TABLE work (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'work' CHECK (kind = 'work'),
    iri text UNIQUE CHECK (iri ~ '^https?://' AND length(iri) <= 2000),
    title text NOT NULL CHECK (has_text(title) AND length(title) <= 1000),
    region text CHECK (region ~ '^[A-Z]{2}(-[A-Z0-9]{1,3})?$'),  -- ISO 3166-1 or -2: DE, DE-NW
    short_title text CHECK (short_title ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(short_title) <= 200),
    owner_id uuid REFERENCES account (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind)
);

-- A document: one edition (Fassung) of a register entry's file, read off its conversion. It
-- carries a draft IRI from its id until it is frozen as a revision (plan M1 9.6), then its IRI.
-- Its rights are its own, taken from the entry when it is made (Gesamtplan §7.4); dates stand as
-- the document gives them (xsd:date, gYearMonth or gYear)
CREATE TABLE document (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'document' CHECK (kind = 'document'),
    source_id uuid NOT NULL REFERENCES source (id),
    conversion_id uuid NOT NULL REFERENCES conversion (id),
    owner_id uuid NOT NULL REFERENCES account (id),
    work_id uuid REFERENCES work (id),
    draft_iri text NOT NULL UNIQUE CHECK (draft_iri ~ '^urn:uuid:[0-9a-f-]{36}$'),
    iri text UNIQUE CHECK (iri ~ '^https?://' AND length(iri) <= 2000),
    edition text CHECK (has_text(edition) AND length(edition) <= 200),
    revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
    frozen_at timestamptz,
    title text CHECK (has_text(title) AND length(title) <= 1000),
    document_type_iri text REFERENCES vocab_concept (iri),  -- a profile's; the app checks which
    sector_scheme text NOT NULL CHECK (sector_scheme = 'https://w3id.org/wlo/curriculum/vocab#EducationSectors'),
    sector_iri text NOT NULL,
    regions text[] NOT NULL DEFAULT '{}' CHECK (all_match(regions, '^[A-Z]{2}(-[A-Z0-9]{1,3})?$')),
    legal_form_scheme text CHECK (legal_form_scheme = 'https://w3id.org/wlo/curriculum/vocab#LegalForms'),
    legal_form_iri text,
    binding_scheme text CHECK (binding_scheme = 'https://w3id.org/wlo/curriculum/vocab#DocumentBindings'),
    binding_iri text,
    lifecycle_scheme text CHECK (lifecycle_scheme = 'https://w3id.org/wlo/curriculum/vocab#Lifecycles'),
    lifecycle_iri text,
    valid_from text CHECK (valid_from ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'),
    valid_until text CHECK (valid_until ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'),
    issued text CHECK (issued ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'),
    rights_status text NOT NULL DEFAULT 'unklar'
        CHECK (rights_status IN ('amtlich', 'offen_lizenziert', 'geschuetzt', 'unklar')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    -- anchors name the document with its conversion, so they name blocks of that one (0015)
    UNIQUE (id, conversion_id),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (sector_scheme, sector_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (legal_form_scheme, legal_form_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (binding_scheme, binding_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (lifecycle_scheme, lifecycle_iri) REFERENCES vocab_concept (scheme_iri, iri),
    CHECK ((legal_form_scheme IS NULL) = (legal_form_iri IS NULL)),
    CHECK ((binding_scheme IS NULL) = (binding_iri IS NULL)),
    CHECK ((lifecycle_scheme IS NULL) = (lifecycle_iri IS NULL)),
    CHECK (frozen_at IS NULL OR iri IS NOT NULL)  -- frozen, a document has its IRI
);
CREATE INDEX document_owner ON document (owner_id);
CREATE INDEX document_source ON document (source_id);

-- What X1 found of the document's own terms (konzept §12.2): its words for profile values, the
-- new terms it brings for the editors' review list, and its tables' columns
CREATE TABLE document_profile (
    document_id uuid PRIMARY KEY REFERENCES document (id) ON DELETE CASCADE,
    term_mappings jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(term_mappings) = 'array'),
    new_terms jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(new_terms) = 'array'),
    table_schemas jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(table_schemas) = 'array')
);

-- What a document stands for (cur:represents): a curriculum, a competency framework, a
-- qualification or an assessment (the kinds X1 names, app/domain/l1.py); a document names each
-- of its own by a key of its own. Placements over many documents follow in M2/M3
CREATE TABLE specification (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'specification' CHECK (kind = 'specification'),
    spec_kind text NOT NULL CHECK (spec_kind IN (
        'curriculum', 'competencyFramework', 'qualificationSpecification', 'assessmentSpecification'
    )),
    title text NOT NULL CHECK (has_text(title) AND length(title) <= 1000),
    field_text text CHECK (length(field_text) <= 2000),  -- the subject or field, as written
    applicability jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(applicability) = 'object'),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind)
);

CREATE TABLE document_specification (
    document_id uuid NOT NULL REFERENCES document (id) ON DELETE CASCADE,
    specification_id uuid NOT NULL REFERENCES specification (id),
    key text NOT NULL CHECK (has_text(key) AND length(key) <= 100),
    PRIMARY KEY (document_id, specification_id),
    UNIQUE (document_id, key)
);
CREATE INDEX document_specification_of ON document_specification (specification_id);

CREATE TABLE variant (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'variant' CHECK (kind = 'variant'),
    specification_id uuid NOT NULL REFERENCES specification (id) ON DELETE CASCADE,
    key text NOT NULL CHECK (has_text(key) AND length(key) <= 100),
    label text NOT NULL CHECK (has_text(label) AND length(label) <= 500),
    variant_kind_scheme text NOT NULL
        CHECK (variant_kind_scheme = 'https://w3id.org/wlo/curriculum/vocab#VariantKinds'),
    variant_kind_iri text NOT NULL,
    UNIQUE (specification_id, key),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (variant_kind_scheme, variant_kind_iri) REFERENCES vocab_concept (scheme_iri, iri)
);

-- One stage of the pipeline on a document (cur:ExtractionRun): which model and prompt, which
-- profile and lexicon release, where its raw answers lie (runs/<run-id>/<stage>/<n>.json). How a
-- run ends, and what it cost, come with the stages that run (plan M1 5, 6.6)
CREATE TABLE extraction_run (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'extraction_run' CHECK (kind = 'extraction_run'),
    document_id uuid NOT NULL REFERENCES document (id) ON DELETE CASCADE,
    job_id uuid REFERENCES job (id),
    stage_scheme text NOT NULL CHECK (stage_scheme = 'https://w3id.org/wlo/curriculum/vocab#Stages'),
    stage_iri text NOT NULL,
    model text CHECK (length(model) BETWEEN 1 AND 200),
    prompt_version text CHECK (length(prompt_version) BETWEEN 1 AND 100),
    profile_version text CHECK (length(profile_version) BETWEEN 1 AND 100),
    lexicon_release integer REFERENCES vocab_release (id),
    raw_response_key text CHECK (length(raw_response_key) BETWEEN 1 AND 512),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    -- what a run made names it with its document, so it names a run of that document (0014, 0015)
    UNIQUE (document_id, id),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (stage_scheme, stage_iri) REFERENCES vocab_concept (scheme_iri, iri),
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);
CREATE INDEX extraction_run_of_job ON extraction_run (job_id) WHERE job_id IS NOT NULL;
