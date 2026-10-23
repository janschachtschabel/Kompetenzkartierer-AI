-- The conversion of a register file into blocks (X0; plan M1, 3.5). A file, shared across
-- accounts by its SHA-256, is converted once by each engine; who may see the conversion is
-- decided at the register entries that hold the file, never here. The lists match
-- app/conversion/base.py (engines, block kinds) and app/db/conversions.py (states, reasons).
CREATE TABLE conversion (
    id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'conversion' CHECK (kind = 'conversion'),
    source_file_id uuid NOT NULL REFERENCES source_file (id),
    engine text NOT NULL CHECK (engine IN ('pdfplumber')),
    engine_version text CHECK (length(engine_version) BETWEEN 1 AND 40),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')),
    error_code text CHECK (error_code IN (
        'unreadable', 'too_many_pages', 'needs_ocr', 'empty', 'timed_out', 'died', 'not_pdf', 'file_gone'
    )),
    account_id uuid REFERENCES account (id),  -- who asked for it: its pages are booked to them
    job_id uuid REFERENCES job (id),  -- the job converting it, the last one asked
    pages integer CHECK (pages >= 0),
    printed_pages jsonb CHECK (jsonb_typeof(printed_pages) = 'array'),  -- per page, or null
    findings jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(findings) = 'array'),
    markdown text,  -- the blocks for a reader, each behind its ID as a comment
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE (source_file_id, engine),
    FOREIGN KEY (id, kind) REFERENCES entity (id, kind),
    CHECK ((status = 'failed') = (error_code IS NOT NULL)),
    CHECK ((status = 'pending') = (finished_at IS NULL)),
    CHECK ((status = 'done') = (pages IS NOT NULL)),
    CHECK (status <> 'done' OR (engine_version IS NOT NULL AND printed_pages IS NOT NULL AND markdown IS NOT NULL))
);
CREATE INDEX conversion_job ON conversion (job_id);

-- A block as X0 names it, p<page>-b<n> (cur-shapes.ttl), at its place in the reading order
CREATE TABLE document_block (
    conversion_id uuid NOT NULL REFERENCES conversion (id) ON DELETE CASCADE,
    block_id text NOT NULL CHECK (block_id ~ '^p[0-9]+-b[0-9]+$'),
    page integer NOT NULL CHECK (page >= 1),
    seq integer NOT NULL CHECK (seq >= 1),
    kind text NOT NULL CHECK (kind IN ('text', 'table', 'page_header', 'page_footer')),
    text text NOT NULL,
    x0 real NOT NULL,
    top real NOT NULL,
    x1 real NOT NULL,
    bottom real NOT NULL,
    font_size real CHECK (font_size > 0),
    bold boolean NOT NULL,
    italic boolean NOT NULL,
    cells jsonb CHECK (jsonb_typeof(cells) = 'array'),  -- a table's, each T<n>:r<i>c<j>
    PRIMARY KEY (conversion_id, block_id),
    UNIQUE (conversion_id, seq),
    CHECK ((kind = 'table') = (cells IS NOT NULL))
);
CREATE INDEX document_block_page ON document_block (conversion_id, page, seq);

-- The pages a conversion booked, once: a job run again books nothing more. Billable only for an
-- engine that costs (pdfplumber does not); quotas follow with the accounting (plan M1, 5)
CREATE TABLE conversion_usage (
    conversion_id uuid PRIMARY KEY REFERENCES conversion (id),
    account_id uuid REFERENCES account (id),
    engine text NOT NULL CHECK (engine IN ('pdfplumber')),
    pages integer NOT NULL CHECK (pages >= 0),
    billable boolean NOT NULL,
    booked_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX conversion_usage_account ON conversion_usage (account_id, booked_at);
