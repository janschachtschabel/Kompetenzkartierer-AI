-- Where the first layer's values were found, the frame parts X3 reads, and what X5 finds of it
-- all (plan M1 4.4, konzept §13, cur-shapes.ttl). Every value stands on its source: an anchor
-- names its page, or the page the document prints, and the blocks of the document's conversion it
-- was found in (p<page>-b<n>, by the conversion's own blocks). One taken away takes its anchors.

-- What X3 finds in a document's frame besides statements (ontology/schemas/x3-rahmenteile.schema.json):
-- a competency or level model, operators, a legend, rules - each as X3 gives it, with anchors. Its
-- typed tables follow in M3; its statements are statements at the frame's node
CREATE TABLE frame_part (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'frame_part' CHECK (kind = 'frame_part'),
    document_id uuid NOT NULL REFERENCES document (id) ON DELETE CASCADE,
    part_kind text NOT NULL CHECK (part_kind IN (
        'competencyModels', 'levelModels', 'operators', 'crossCuttingLegend', 'rules'
    )),
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
    origin_scheme text NOT NULL CHECK (origin_scheme = 'https://w3id.org/wlo/curriculum/vocab#Origins'),
    origin_iri text NOT NULL,
    review_status_scheme text NOT NULL
        CHECK (review_status_scheme = 'https://w3id.org/wlo/curriculum/vocab#ReviewStatuses'),
    review_status_iri text NOT NULL,
    revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
    run_id uuid REFERENCES extraction_run (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, id),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (origin_scheme, origin_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (review_status_scheme, review_status_iri) REFERENCES vocab_concept (scheme_iri, iri)
);
CREATE INDEX frame_part_of_document ON frame_part (document_id);

-- An anchor (cur:SourceAnchor) of one node, statement or frame part of its document. It names the
-- document with the document's conversion, so its blocks are that conversion's
CREATE TABLE anchor (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'anchor' CHECK (kind = 'anchor'),
    document_id uuid NOT NULL,
    conversion_id uuid NOT NULL,
    node_id uuid,
    statement_id uuid,
    frame_part_id uuid,
    page_start integer CHECK (page_start >= 1),  -- physical, from 1
    page_end integer,
    printed_page text CHECK (has_text(printed_page) AND length(printed_page) <= 20),
    quote text CHECK (length(quote) <= 20000),
    match_kind_scheme text CHECK (match_kind_scheme = 'https://w3id.org/wlo/curriculum/vocab#MatchKinds'),
    match_kind_iri text,
    match_score numeric CHECK (match_score BETWEEN 0 AND 1),
    char_start integer CHECK (char_start >= 0),
    char_end integer,
    table_cell text CHECK (table_cell ~ '^T[0-9]+:r[0-9]+c[0-9]+$'),  -- cur:tableCell, "T4:r3c2"
    section_path text CHECK (length(section_path) <= 2000),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, conversion_id),
    FOREIGN KEY (document_id, conversion_id) REFERENCES document (id, conversion_id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, node_id) REFERENCES node (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, statement_id) REFERENCES statement (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, frame_part_id) REFERENCES frame_part (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (match_kind_scheme, match_kind_iri) REFERENCES vocab_concept (scheme_iri, iri),
    CHECK (num_nonnulls(node_id, statement_id, frame_part_id) = 1),
    CHECK (page_start IS NOT NULL OR printed_page IS NOT NULL),
    CHECK (page_end >= page_start),
    CHECK (char_end >= char_start),
    CHECK ((match_kind_scheme IS NULL) = (match_kind_iri IS NULL))
);
CREATE INDEX anchor_of_node ON anchor (node_id) WHERE node_id IS NOT NULL;
CREATE INDEX anchor_of_statement ON anchor (statement_id) WHERE statement_id IS NOT NULL;
CREATE INDEX anchor_of_frame_part ON anchor (frame_part_id) WHERE frame_part_id IS NOT NULL;

CREATE TABLE anchor_block (
    anchor_id uuid NOT NULL,
    conversion_id uuid NOT NULL,
    block_id text NOT NULL CHECK (block_id ~ '^p[0-9]+-b[0-9]+$'),
    PRIMARY KEY (anchor_id, block_id),
    FOREIGN KEY (anchor_id, conversion_id) REFERENCES anchor (id, conversion_id) ON DELETE CASCADE,
    FOREIGN KEY (conversion_id, block_id) REFERENCES document_block (conversion_id, block_id)
);
CREATE INDEX anchor_block_of_block ON anchor_block (conversion_id, block_id);

-- What X5 finds (plan M1 8): which rule - a shape's IRI or a rule's name - how grave, and what
-- about: a row of the first layer, or the document as a whole. A second run of X5 replaces the
-- findings of the run before (plan M1 8.5)
CREATE TABLE validation_finding (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES document (id) ON DELETE CASCADE,
    run_id uuid REFERENCES extraction_run (id) ON DELETE CASCADE,
    rule text NOT NULL CHECK (has_text(rule) AND length(rule) <= 500),
    severity text NOT NULL CHECK (severity IN ('violation', 'warning', 'info')),
    focus_id uuid NOT NULL REFERENCES entity (id),
    path text CHECK (length(path) <= 500),  -- the property the finding is about, where it is one
    message text NOT NULL CHECK (has_text(message) AND length(message) <= 4000),
    details jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(details) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX validation_finding_of_document ON validation_finding (document_id);
CREATE INDEX validation_finding_of_run ON validation_finding (run_id);
