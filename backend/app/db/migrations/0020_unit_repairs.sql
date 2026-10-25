-- How often X6 asked the model again for a unit (plan M1 8b; konzept §13.2: "0-2"): a repair writes the
-- unit anew and counts it here, in the transaction that writes its statements; a unit repaired twice is
-- left to the editors, whatever its findings
ALTER TABLE extraction_unit ADD COLUMN repairs smallint NOT NULL DEFAULT 0 CHECK (repairs BETWEEN 0 AND 2);
