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
    rule_id text CHECK (has_text(rule_id) AND length(rule_id) <= 200),
    revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
    run_id uuid,  -- the run that made it; a run taken away leaves what it made
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, id),
    FOREIGN KEY (document_id, run_id) REFERENCES extraction_run (document_id, id) ON DELETE SET NULL (run_id),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (origin_scheme, origin_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (review_status_scheme, review_status_iri) REFERENCES vocab_concept (scheme_iri, iri),
    -- one a rule gave names the rule, as a node does (0014)
    CHECK ((origin_iri = 'https://w3id.org/wlo/curriculum/vocab#orig_rule') = (rule_id IS NOT NULL))
);
CREATE INDEX frame_part_of_run ON frame_part (run_id) WHERE run_id IS NOT NULL;

-- An anchor (cur:SourceAnchor) of one node, statement, frame part or specification of its
-- document - or, naming none, of the document itself: where X1 read its title or dates. It names
-- the document with the document's conversion, so its blocks are that conversion's
CREATE TABLE anchor (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'anchor' CHECK (kind = 'anchor'),
    document_id uuid NOT NULL,
    conversion_id uuid NOT NULL,
    node_id uuid,
    statement_id uuid,
    frame_part_id uuid,
    specification_id uuid,
    page_start integer CHECK (page_start >= 1),  -- physical, from 1
    page_end integer,
    printed_page text CHECK (has_text(printed_page) AND length(printed_page) <= 20),
    quote text CHECK (length(quote) <= 20000),
    match_kind_scheme text CHECK (match_kind_scheme = 'https://w3id.org/wlo/curriculum/vocab#MatchKinds'),
    match_kind_iri text,
    match_score numeric CHECK (match_score BETWEEN 0 AND 1),
    char_start integer CHECK (char_start >= 0),
    char_end integer CHECK (char_end >= 0),
    table_cell text CHECK (table_cell ~ '^T[0-9]+:r[0-9]+c[0-9]+$'),  -- cur:tableCell, "T4:r3c2"
    section_path text CHECK (length(section_path) <= 2000),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, conversion_id),
    FOREIGN KEY (document_id, conversion_id) REFERENCES document (id, conversion_id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, node_id) REFERENCES node (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, statement_id) REFERENCES statement (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, frame_part_id) REFERENCES frame_part (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, specification_id) REFERENCES specification (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (match_kind_scheme, match_kind_iri) REFERENCES vocab_concept (scheme_iri, iri),
    CHECK (num_nonnulls(node_id, statement_id, frame_part_id, specification_id) <= 1),
    CHECK (page_start IS NOT NULL OR printed_page IS NOT NULL),
    CHECK (page_end >= page_start),
    CHECK (page_end IS NULL OR page_start IS NOT NULL),  -- an end of a range it begins
    CHECK (char_end >= char_start),
    CHECK ((match_kind_scheme IS NULL) = (match_kind_iri IS NULL))
);
CREATE INDEX anchor_of_document ON anchor (document_id, conversion_id);
CREATE INDEX anchor_of_node ON anchor (node_id) WHERE node_id IS NOT NULL;
CREATE INDEX anchor_of_statement ON anchor (statement_id) WHERE statement_id IS NOT NULL;
CREATE INDEX anchor_of_frame_part ON anchor (frame_part_id) WHERE frame_part_id IS NOT NULL;
CREATE INDEX anchor_of_specification ON anchor (specification_id) WHERE specification_id IS NOT NULL;

-- A statement stands on its source (cur:anchor, one at least): when its transaction commits it
-- has an anchor, and its last one stays with it, as its last addressee does (0014)
CREATE FUNCTION statement_anchored() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target uuid;
BEGIN
    IF TG_TABLE_NAME = 'statement' THEN
        target := NEW.id;
    ELSE
        target := OLD.statement_id;
        IF NOT EXISTS (SELECT FROM statement WHERE id = target) THEN
            RETURN NULL;  -- a node's or frame part's, or gone with its statement
        END IF;
        PERFORM read_committed_alone('an anchor is taken away from its statement');
        -- locked, so another taking one away waits for this one and then counts what it left
        PERFORM FROM statement WHERE id = target FOR NO KEY UPDATE;
    END IF;
    IF EXISTS (SELECT FROM statement WHERE id = target)
        AND NOT EXISTS (SELECT FROM anchor WHERE statement_id = target) THEN
        RAISE EXCEPTION 'statement % has no anchor', target USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END
$$;
CREATE CONSTRAINT TRIGGER statement_anchored AFTER INSERT ON statement
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION statement_anchored();
CREATE CONSTRAINT TRIGGER statement_anchor_kept AFTER DELETE OR UPDATE OF statement_id ON anchor
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION statement_anchored();

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
    run_id uuid,  -- the run of X5 that found it; its findings go with it
    rule text NOT NULL CHECK (has_text(rule) AND length(rule) <= 500),
    severity text NOT NULL CHECK (severity IN ('violation', 'warning', 'info')),
    focus_id uuid NOT NULL REFERENCES entity (id),
    path text CHECK (length(path) <= 500),  -- the property the finding is about, where it is one
    message text NOT NULL CHECK (has_text(message) AND length(message) <= 4000),
    details jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(details) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (document_id, run_id) REFERENCES extraction_run (document_id, id) ON DELETE CASCADE
);
CREATE INDEX validation_finding_of_document ON validation_finding (document_id);
CREATE INDEX validation_finding_of_run ON validation_finding (run_id) WHERE run_id IS NOT NULL;
