-- A document's structure and its statements (plan M1 4.3, konzept §5, cur-shapes.ttl): nodes in
-- a tree within one document, statements at nodes, each with its addressees. Every value says
-- where it came from (cv:Origins) and how far it is reviewed (cv:ReviewStatuses); one a rule
-- gave names the rule. A node's depth follows from its parents and is not kept. ``revision``
-- counts a row's changes, for the editors' writes to check against (plan M1 9.3).

CREATE TABLE node (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'node' CHECK (kind = 'node'),
    document_id uuid NOT NULL REFERENCES document (id) ON DELETE CASCADE,
    parent_id uuid,
    position integer NOT NULL CHECK (position >= 1),  -- among its siblings, from 1
    function_scheme text NOT NULL CHECK (function_scheme = 'https://w3id.org/wlo/curriculum/vocab#NodeFunctions'),
    function_iri text NOT NULL,
    node_type_iri text REFERENCES vocab_concept (iri),  -- a profile's, under the function (trigger below)
    code text CHECK (has_text(code) AND length(code) <= 100),
    code_assigned boolean NOT NULL DEFAULT false,  -- the pipeline's, from the position (cur:codeAssigned)
    original_title text CHECK (has_text(original_title) AND length(original_title) <= 2000),
    title_language text NOT NULL DEFAULT 'de' CHECK (title_language ~ '^[a-z]{2,3}(-[A-Za-z0-9]{1,8})*$'),
    obligation_scheme text CHECK (obligation_scheme = 'https://w3id.org/wlo/curriculum/vocab#Obligations'),
    obligation_iri text,
    scope_share_scheme text CHECK (scope_share_scheme = 'https://w3id.org/wlo/curriculum/vocab#ScopeShares'),
    scope_share_iri text,
    extraction_depth_scheme text
        CHECK (extraction_depth_scheme = 'https://w3id.org/wlo/curriculum/vocab#ExtractionDepths'),
    extraction_depth_iri text,
    applies_to uuid[] NOT NULL DEFAULT '{}',  -- specifications or variants of the document
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
    -- deferrable, so the editors may reorder siblings within one transaction (plan M1 9)
    UNIQUE NULLS NOT DISTINCT (document_id, parent_id, position) DEFERRABLE,
    FOREIGN KEY (document_id, parent_id) REFERENCES node (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, run_id) REFERENCES extraction_run (document_id, id) ON DELETE SET NULL (run_id),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (function_scheme, function_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (obligation_scheme, obligation_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (scope_share_scheme, scope_share_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (extraction_depth_scheme, extraction_depth_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (origin_scheme, origin_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (review_status_scheme, review_status_iri) REFERENCES vocab_concept (scheme_iri, iri),
    CHECK ((obligation_scheme IS NULL) = (obligation_iri IS NULL)),
    CHECK ((scope_share_scheme IS NULL) = (scope_share_iri IS NULL)),
    CHECK ((extraction_depth_scheme IS NULL) = (extraction_depth_iri IS NULL)),
    CHECK (parent_id <> id),
    CHECK (NOT code_assigned OR code IS NOT NULL),
    CHECK ((origin_iri = 'https://w3id.org/wlo/curriculum/vocab#orig_rule') = (rule_id IS NOT NULL))
);
CREATE INDEX node_of_run ON node (run_id) WHERE run_id IS NOT NULL;

-- A node comes to lie under itself nowhere, however it is written: checked once its statement
-- has written all its rows (nodes inserted in a circle at once too). Writes to one document's
-- tree wait for each other, so two moves that would close a circle between them do not pass side
-- by side - under read committed, where each sees the other's once it waits; under repeatable
-- read neither would, so a move there is refused (serializable finds the conflict itself). Who
-- writes a tree takes its lock first (app/db/nodes.py, lock_tree): taken here, after the row's
-- own lock, two moves could wait for each other the other way round
CREATE FUNCTION node_without_cycle() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.parent_id IS NULL THEN
        RETURN NULL;
    END IF;
    IF TG_OP = 'UPDATE' AND current_setting('transaction_isolation') = 'repeatable read' THEN
        RAISE EXCEPTION 'a node is moved under read committed or serializable, not repeatable read'
            USING ERRCODE = 'invalid_transaction_state';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('node-tree:' || NEW.document_id::text, 0));
    IF EXISTS (
        WITH RECURSIVE up (id) AS (
            SELECT NEW.parent_id
            UNION
            SELECT node.parent_id FROM node JOIN up ON node.id = up.id WHERE node.parent_id IS NOT NULL
        )
        SELECT FROM up WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'node % would lie under itself', NEW.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END
$$;
CREATE CONSTRAINT TRIGGER node_without_cycle AFTER INSERT OR UPDATE OF parent_id ON node
    FOR EACH ROW EXECUTE FUNCTION node_without_cycle();

-- A profile value refines the core value it stands beside: a node type lies under the node's
-- function, a subkind under its statement's kind (skos:broader, cur-shapes.ttl). Which profile
-- a value may come from, the app checks (app/db/nodes.py)
CREATE FUNCTION refines(value_iri text, core_iri text) RETURNS boolean
    LANGUAGE sql STABLE PARALLEL SAFE
    RETURN value_iri IS NULL OR EXISTS (SELECT FROM vocab_concept WHERE iri = value_iri AND core_iri = ANY (broader));

CREATE FUNCTION node_type_fits() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT refines(NEW.node_type_iri, NEW.function_iri) THEN
        RAISE EXCEPTION 'node type % does not lie under the function %', NEW.node_type_iri, NEW.function_iri
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER node_type_fits BEFORE INSERT OR UPDATE OF node_type_iri, function_iri ON node
    FOR EACH ROW EXECUTE FUNCTION node_type_fits();

CREATE TABLE statement (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'statement' CHECK (kind = 'statement'),
    document_id uuid NOT NULL,
    node_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 1),  -- among the node's statements, from 1
    verbatim text NOT NULL CHECK (has_text(verbatim) AND length(verbatim) <= 20000),
    language text NOT NULL DEFAULT 'de' CHECK (language ~ '^[a-z]{2,3}(-[A-Za-z0-9]{1,8})*$'),
    lead_in text CHECK (has_text(lead_in) AND length(lead_in) <= 2000),  -- "Die Schülerinnen und Schüler …"
    statement_kind_scheme text NOT NULL
        CHECK (statement_kind_scheme = 'https://w3id.org/wlo/curriculum/vocab#StatementKinds'),
    statement_kind_iri text NOT NULL,
    subkind_iri text REFERENCES vocab_concept (iri),  -- a profile's, under the kind (trigger below)
    obligation_scheme text CHECK (obligation_scheme = 'https://w3id.org/wlo/curriculum/vocab#Obligations'),
    obligation_iri text,
    origin_scheme text NOT NULL CHECK (origin_scheme = 'https://w3id.org/wlo/curriculum/vocab#Origins'),
    origin_iri text NOT NULL,
    review_status_scheme text NOT NULL
        CHECK (review_status_scheme = 'https://w3id.org/wlo/curriculum/vocab#ReviewStatuses'),
    review_status_iri text NOT NULL,
    rule_id text CHECK (has_text(rule_id) AND length(rule_id) <= 200),
    text_hash text NOT NULL CHECK (text_hash ~ '^[0-9a-f]{64}$'),  -- cur:textHash (app/domain/wording.py)
    -- the wording's other fields X4 gives (level, time, context, example, purpose ...)
    details jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(details) = 'object'),
    layout_markers text[] NOT NULL DEFAULT '{}',  -- cv:LayoutMarkers
    revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
    run_id uuid,  -- the run that made it; a run taken away leaves what it made
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, id),
    UNIQUE (node_id, position) DEFERRABLE,
    FOREIGN KEY (document_id, node_id) REFERENCES node (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, run_id) REFERENCES extraction_run (document_id, id) ON DELETE SET NULL (run_id),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    FOREIGN KEY (statement_kind_scheme, statement_kind_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (obligation_scheme, obligation_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (origin_scheme, origin_iri) REFERENCES vocab_concept (scheme_iri, iri),
    FOREIGN KEY (review_status_scheme, review_status_iri) REFERENCES vocab_concept (scheme_iri, iri),
    CHECK ((obligation_scheme IS NULL) = (obligation_iri IS NULL)),
    CHECK ((origin_iri = 'https://w3id.org/wlo/curriculum/vocab#orig_rule') = (rule_id IS NOT NULL))
);
CREATE INDEX statement_of_run ON statement (run_id) WHERE run_id IS NOT NULL;
CREATE INDEX statement_text_hash ON statement (text_hash);

CREATE FUNCTION subkind_fits() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT refines(NEW.subkind_iri, NEW.statement_kind_iri) THEN
        RAISE EXCEPTION 'subkind % does not lie under the kind %', NEW.subkind_iri, NEW.statement_kind_iri
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER subkind_fits BEFORE INSERT OR UPDATE OF subkind_iri, statement_kind_iri ON statement
    FOR EACH ROW EXECUTE FUNCTION subkind_fits();

-- Whom a statement addresses (cur:addressee): one at least, when its transaction commits
CREATE TABLE statement_addressee (
    statement_id uuid NOT NULL REFERENCES statement (id) ON DELETE CASCADE,
    addressee_scheme text NOT NULL CHECK (addressee_scheme = 'https://w3id.org/wlo/curriculum/vocab#Addressees'),
    addressee_iri text NOT NULL,
    PRIMARY KEY (statement_id, addressee_iri),
    FOREIGN KEY (addressee_scheme, addressee_iri) REFERENCES vocab_concept (scheme_iri, iri)
);

CREATE FUNCTION statement_addressed() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target uuid;
BEGIN
    IF TG_TABLE_NAME = 'statement' THEN
        target := NEW.id;
    ELSE
        target := OLD.statement_id;
    END IF;
    IF EXISTS (SELECT FROM statement WHERE id = target)
        AND NOT EXISTS (SELECT FROM statement_addressee WHERE statement_id = target) THEN
        RAISE EXCEPTION 'statement % has no addressee', target USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END
$$;
CREATE CONSTRAINT TRIGGER statement_addressed AFTER INSERT ON statement
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION statement_addressed();
CREATE CONSTRAINT TRIGGER statement_addressee_kept AFTER DELETE OR UPDATE ON statement_addressee
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION statement_addressed();
