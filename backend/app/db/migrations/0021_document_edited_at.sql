-- When an editor last changed what a document says (plan M1 9.3, 9.4; Paket 9 G9): its nodes, statements
-- or their anchors, a statement rejected - not a review status set. X5 is owed again once this is later
-- than the start of its last finished run; none for a document no editor has changed
ALTER TABLE document ADD COLUMN edited_at timestamptz;
