-- A unit of X4 done (plan M1 7b): one of the document's work packages (X2, E1 ...), its statements
-- written in one transaction with this row, so a unit is done whole or not at all, and once per
-- document - a second writer of the same unit fails on the key and takes back what it wrote. What
-- the unit was found to lack are docking points (cur:checkedAbsent). Its run gone, or its node, the
-- unit is open again, and the next extraction asks for it.
CREATE TABLE extraction_unit (
    document_id uuid NOT NULL REFERENCES document (id) ON DELETE CASCADE,
    unit_key text NOT NULL CHECK (unit_key ~ '^E[0-9]{1,6}$'),
    run_id uuid NOT NULL,
    node_id uuid,
    statements integer NOT NULL CHECK (statements >= 0),
    checked_absent text[] NOT NULL DEFAULT '{}',
    finished_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, unit_key),
    FOREIGN KEY (document_id, run_id) REFERENCES extraction_run (document_id, id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, node_id) REFERENCES node (document_id, id) ON DELETE CASCADE
);

CREATE INDEX extraction_unit_run ON extraction_unit (run_id);
CREATE INDEX extraction_unit_node ON extraction_unit (node_id) WHERE node_id IS NOT NULL;

-- What a unit lacks (cur:checkedAbsent): concepts of cv:DockingPoints, which the vocabularies
-- retire but never take away
CREATE FUNCTION docking_points_fit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT FROM unnest(NEW.checked_absent) AS point
        WHERE NOT EXISTS (  -- a NULL is no concept either
            SELECT FROM vocab_concept
            WHERE scheme_iri = 'https://w3id.org/wlo/curriculum/vocab#DockingPoints' AND iri = point
        )
    ) THEN
        RAISE EXCEPTION 'unit % names what is no docking point', NEW.unit_key USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER docking_points_fit BEFORE INSERT OR UPDATE OF checked_absent ON extraction_unit
    FOR EACH ROW EXECUTE FUNCTION docking_points_fit();

-- The order X3 wrote a document's frame parts in - their reading order, which X4's choice lists
-- keep - is theirs to hold: ids of one millisecond sort by their random bits (app/core/ids.py).
-- No frame part is written before X3 (plan M1 7b), so none stands without one
ALTER TABLE frame_part ADD COLUMN position integer NOT NULL CHECK (position >= 1);
ALTER TABLE frame_part ADD CONSTRAINT frame_part_position UNIQUE (document_id, position);
