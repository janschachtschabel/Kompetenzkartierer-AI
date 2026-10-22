-- What an account did, for its limits per minute (app/db/rate_limits.py): uploads, URL imports,
-- starts of model jobs. In the database, so the API replicas share them; a take removes the
-- account's rows older than a minute for its action, so the table stays small.
CREATE TABLE rate_event (
    account_id uuid NOT NULL REFERENCES account (id) ON DELETE CASCADE,
    action text NOT NULL CHECK (action ~ '^[a-z][a-z_]*(\.[a-z][a-z_]*)*$'),
    at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX rate_event_recent ON rate_event (account_id, action, at);
