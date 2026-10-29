-- A document frozen (plan M1 9.6; Paket 9b): the IRIs its nodes and statements get, a mark of the
-- statements an editor wrote, the draft copy's link to the revision it copies - and a frozen
-- document's rows kept as they were written.

-- A node's IRI, the path of codes under its document's (app/domain/iris.py), and the highest number
-- its statements' IRIs (<node>/s-<n>) have been given: kept over draft copies, so none is given twice
ALTER TABLE node
    ADD COLUMN iri text CHECK (iri ~ '^https?://' AND length(iri) <= 2000),
    ADD COLUMN statement_serial integer NOT NULL DEFAULT 0 CHECK (statement_serial >= 0),
    ADD UNIQUE (document_id, iri);

-- An editor's from the first: deleted when taken away, where a run's or a rule's is rejected. Told
-- apart by origin and run before; a draft copy has no runs, so the mark is the statement's own
ALTER TABLE statement
    ADD COLUMN iri text CHECK (iri ~ '^https?://' AND length(iri) <= 2000),
    ADD COLUMN by_hand boolean NOT NULL DEFAULT false,
    ADD UNIQUE (document_id, iri);
UPDATE statement SET by_hand = true
WHERE origin_iri = 'https://w3id.org/wlo/curriculum/vocab#orig_human' AND run_id IS NULL;

-- A draft copy: a new revision of a frozen one, under its IRI. One draft at most is open under an IRI
ALTER TABLE document
    ADD COLUMN copy_of uuid REFERENCES document (id),
    ADD CHECK (copy_of IS DISTINCT FROM id),
    ADD CHECK (copy_of IS NULL OR iri IS NOT NULL);
CREATE INDEX document_copy_of ON document (copy_of) WHERE copy_of IS NOT NULL;
CREATE UNIQUE INDEX document_one_draft ON document (iri) WHERE frozen_at IS NULL AND iri IS NOT NULL;

CREATE FUNCTION document_frozen(of_document uuid) RETURNS boolean
    LANGUAGE sql STABLE PARALLEL SAFE
    RETURN EXISTS (SELECT FROM document WHERE id = of_document AND frozen_at IS NOT NULL);

-- The document a row of the first layer is of: its own column, or its statement's, anchor's or
-- specification's. Gone with a row a cascade took away first, so none - and that one's own
-- trigger has spoken already
CREATE FUNCTION row_document(table_name text, item jsonb) RETURNS uuid
    LANGUAGE sql STABLE PARALLEL SAFE
    RETURN CASE table_name
        WHEN 'statement_addressee'
            THEN (SELECT document_id FROM statement WHERE id = (item ->> 'statement_id')::uuid)
        WHEN 'anchor_block' THEN (SELECT document_id FROM anchor WHERE id = (item ->> 'anchor_id')::uuid)
        WHEN 'variant'
            THEN (SELECT document_id FROM specification WHERE id = (item ->> 'specification_id')::uuid)
        ELSE (item ->> 'document_id')::uuid
    END;

CREATE FUNCTION keep_frozen_rows() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    of_document uuid;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        of_document := row_document(TG_TABLE_NAME, to_jsonb(OLD));
        IF document_frozen(of_document) THEN
            RAISE EXCEPTION 'document % is frozen: its % rows stay as they are', of_document, TG_TABLE_NAME
                USING ERRCODE = 'object_not_in_prerequisite_state';
        END IF;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        of_document := row_document(TG_TABLE_NAME, to_jsonb(NEW));
        IF document_frozen(of_document) THEN
            RAISE EXCEPTION 'document % is frozen: its % rows stay as they are', of_document, TG_TABLE_NAME
                USING ERRCODE = 'object_not_in_prerequisite_state';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END
$$;

CREATE TRIGGER node_stays_frozen BEFORE INSERT OR UPDATE OR DELETE ON node
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_rows();
CREATE TRIGGER statement_stays_frozen BEFORE INSERT OR UPDATE OR DELETE ON statement
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_rows();
CREATE TRIGGER statement_addressee_stays_frozen BEFORE INSERT OR UPDATE OR DELETE ON statement_addressee
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_rows();
CREATE TRIGGER anchor_stays_frozen BEFORE INSERT OR UPDATE OR DELETE ON anchor
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_rows();
CREATE TRIGGER anchor_block_stays_frozen BEFORE INSERT OR UPDATE OR DELETE ON anchor_block
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_rows();
CREATE TRIGGER frame_part_stays_frozen BEFORE INSERT OR UPDATE OR DELETE ON frame_part
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_rows();
CREATE TRIGGER specification_stays_frozen BEFORE INSERT OR UPDATE OR DELETE ON specification
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_rows();
CREATE TRIGGER variant_stays_frozen BEFORE INSERT OR UPDATE OR DELETE ON variant
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_rows();
CREATE TRIGGER document_profile_stays_frozen BEFORE INSERT OR UPDATE OR DELETE ON document_profile
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_rows();

-- The document's own row: frozen, it changes its rights status alone - who may reuse it may change
-- with its source's terms (Paket 9b H1) - and is never taken away
CREATE FUNCTION keep_frozen_document() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.frozen_at IS NOT NULL AND (
        TG_OP = 'DELETE'
        OR to_jsonb(OLD) - 'rights_status' - 'updated_at'
            IS DISTINCT FROM to_jsonb(NEW) - 'rights_status' - 'updated_at'
    ) THEN
        RAISE EXCEPTION 'document % is frozen: it changes its rights status alone', OLD.id
            USING ERRCODE = 'object_not_in_prerequisite_state';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER document_stays_frozen BEFORE UPDATE OR DELETE ON document
    FOR EACH ROW EXECUTE FUNCTION keep_frozen_document();
