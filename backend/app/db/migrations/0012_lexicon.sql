-- The lexicon (plan M1 4.7, konzept §12.1): each sector's terminology profile and its cues, as
-- python -m app.vocab.load reads them from ontology/profile, in the release of the vocabularies
-- (app/vocab/loader.py, store.py). A cue the files no longer hold is retired by that release,
-- like a concept; its IRI stays its key (the editors' decisions refer to it, plan M1 10.3).

-- A profile names its sector (cur:profileScope); its values - node types, statement subkinds,
-- document types - are named under its namespace, the profile's IRI up to its last '#' or '/'
-- (app/vocab/lookup.py reads them so). One active profile for each sector.
CREATE TABLE terminology_profile (
    iri text PRIMARY KEY CHECK (iri ~ '^https?://'),
    namespace text NOT NULL CHECK (namespace ~ '[#/]$'),
    sector_scheme text NOT NULL CHECK (sector_scheme = 'https://w3id.org/wlo/curriculum/vocab#EducationSectors'),
    sector_iri text NOT NULL,
    labels jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(labels) = 'object'),  -- {language: label}
    retired_in integer REFERENCES vocab_release (id),
    FOREIGN KEY (sector_scheme, sector_iri) REFERENCES vocab_concept (scheme_iri, iri),
    CHECK (starts_with(iri, namespace) AND length(iri) > length(namespace))
);
CREATE UNIQUE INDEX terminology_profile_of_sector ON terminology_profile (sector_iri) WHERE retired_in IS NULL;

-- A cue: a word, a pattern (the syntax of Python's re, searched with a time limit) or a layout
-- signal, and what it points to. Its targets are IRIs without a foreign key: 226 of 1,460 name
-- a class, a property or a scheme, no concept; the reader checks each is typed in the model.
-- So are its places (cv:Occurrences) and the scope's regions, document types, institution types
-- and subjects. Dates stand as written (xsd:date, gYearMonth or gYear).
CREATE TABLE lexical_cue (
    iri text PRIMARY KEY CHECK (iri ~ '^https?://'),
    profile_iri text NOT NULL REFERENCES terminology_profile (iri),
    surface_form text,
    pattern text,
    layout_signal text,
    role_scheme text NOT NULL CHECK (role_scheme = 'https://w3id.org/wlo/curriculum/vocab#CueRoles'),
    role_iri text NOT NULL,
    kind_scheme text NOT NULL CHECK (kind_scheme = 'https://w3id.org/wlo/curriculum/vocab#CueKinds'),
    kind_iri text NOT NULL,
    maps_to text[] NOT NULL CHECK (cardinality(maps_to) >= 1),
    also_maps_to text[] NOT NULL DEFAULT '{}',  -- a homonym's other target
    occurs_in text[] NOT NULL DEFAULT '{}',
    scope_regions text[] NOT NULL DEFAULT '{}',
    scope_document_types text[] NOT NULL DEFAULT '{}',
    scope_institution_types text[] NOT NULL DEFAULT '{}',
    scope_subjects text[] NOT NULL DEFAULT '{}',
    scope_issuers text[] NOT NULL DEFAULT '{}',  -- as the files write them, text
    plan_generations text[] NOT NULL DEFAULT '{}',
    valid_from text CHECK (valid_from ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'),
    valid_until text CHECK (valid_until ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'),
    strength numeric CHECK (strength BETWEEN 0 AND 1),
    verified boolean NOT NULL DEFAULT false,  -- checked against an original; unsaid, it was not
    recognition_hints jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(recognition_hints) = 'object'),
    negative_hints jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(negative_hints) = 'object'),
    positive_examples text[] NOT NULL DEFAULT '{}',
    negative_examples text[] NOT NULL DEFAULT '{}',
    -- what else the files say of it (prov:wasDerivedFrom, skos:exactMatch, a profile's own
    -- properties), as vocab_concept.properties holds it
    properties jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(properties) = 'object'),
    retired_in integer REFERENCES vocab_release (id),
    FOREIGN KEY (role_scheme, role_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (kind_scheme, kind_iri) REFERENCES vocab_concept (scheme_iri, iri),
    CHECK (num_nonnulls(surface_form, pattern, layout_signal) >= 1)
);
CREATE INDEX lexical_cue_of_profile ON lexical_cue (profile_iri) WHERE retired_in IS NULL;
