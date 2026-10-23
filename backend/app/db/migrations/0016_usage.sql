-- The accounting of the model's work (plan M1 5.4-5.6, Festlegungen "Kosten"): what an account
-- may spend, what each request to the model cost, and what is held for the requests not yet
-- answered. The budget is tokens, input and output together; what is left of it is the limit
-- less the costs and the reservations, summed under the quota row's lock (app/usage/ledger.py),
-- so there is no counter to drift from the rows.

-- An account's limits: NULL is none, for any role, an admin's too (plan M1 5.6). An account
-- without a row may spend nothing: the model's work is never free. Pages count for an engine
-- that costs (conversion_usage.billable); pdfplumber does not, so nothing holds to them yet
CREATE TABLE quota (
    account_id uuid PRIMARY KEY REFERENCES account (id) ON DELETE CASCADE,
    token_limit bigint CHECK (token_limit >= 0),
    page_limit bigint CHECK (page_limit >= 0)
);

-- What one request to the model cost, booked once it is answered: its input (of it, read from
-- the provider's cache), its output, the requests answered. One sent and never answered is
-- booked at what was held for it, estimated: the provider may have counted it. No key to the
-- job or the run: like the audit log, the record outlives them; the account it is charged to
-- stays as long as it does
CREATE TABLE llm_usage (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES account (id),
    job_id uuid,
    run_id uuid,  -- extraction_run, where a stage of the pipeline asked
    purpose text NOT NULL CHECK (purpose ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$' AND length(purpose) <= 100),
    model text NOT NULL CHECK (length(model) BETWEEN 1 AND 200),
    input_tokens bigint NOT NULL CHECK (input_tokens >= 0),
    cached_input_tokens bigint NOT NULL CHECK (cached_input_tokens >= 0),
    output_tokens bigint NOT NULL CHECK (output_tokens >= 0),
    requests integer NOT NULL CHECK (requests >= 0),
    unanswered_requests integer NOT NULL CHECK (unanswered_requests >= 0),
    estimated boolean NOT NULL,  -- no default: the writer says whether it counted or held
    booked_at timestamptz NOT NULL DEFAULT now(),
    CHECK (cached_input_tokens <= input_tokens)
);
CREATE INDEX llm_usage_account ON llm_usage (account_id, booked_at);

-- What a request to the model may yet cost, held from its account's budget before it is sent:
-- its input as counted, its output up to the cap. Its booking takes it away; a job that ends
-- holding one has it booked as spent, never let go, so job and account stay until then. It
-- names what a booking of it names
CREATE TABLE usage_reservation (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES account (id),
    job_id uuid NOT NULL REFERENCES job (id),
    run_id uuid,
    purpose text NOT NULL CHECK (purpose ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$' AND length(purpose) <= 100),
    model text NOT NULL CHECK (length(model) BETWEEN 1 AND 200),
    input_tokens bigint NOT NULL CHECK (input_tokens > 0),
    output_tokens bigint NOT NULL CHECK (output_tokens > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX usage_reservation_account ON usage_reservation (account_id);
CREATE INDEX usage_reservation_job ON usage_reservation (job_id);
