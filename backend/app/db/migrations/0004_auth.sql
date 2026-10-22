-- Accounts, their roles and API keys (app/db/accounts.py), the audit log, failed sign-ins.
-- An admin hands out tokens; the server keeps only their HMAC under API_KEY_PEPPER.
CREATE TABLE account (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    created_at timestamptz NOT NULL DEFAULT now(),
    disabled_at timestamptz
);
CREATE UNIQUE INDEX account_name ON account (lower(name));

CREATE TABLE role_grant (
    account_id uuid NOT NULL REFERENCES account (id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('admin', 'redaktion', 'nutzer')),
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, role)
);

CREATE TABLE api_key (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES account (id) ON DELETE CASCADE,
    key_hash bytea NOT NULL UNIQUE CHECK (length(key_hash) = 32),
    label text NOT NULL DEFAULT '' CHECK (length(label) <= 200),
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at timestamptz
);
CREATE INDEX api_key_account ON api_key (account_id);

-- Who did what; no foreign key, so the record outlives the account
CREATE TABLE audit_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at timestamptz NOT NULL DEFAULT now(),
    actor_id uuid,
    actor_name text,
    action text NOT NULL,
    subject text,
    details jsonb NOT NULL DEFAULT '{}',
    request_id text
);

-- Failed sign-ins per source (client address), for the limit; old rows go as new ones come
CREATE TABLE auth_failure (
    source text NOT NULL CHECK (length(source) <= 64),  -- an address, an IPv6 /64 or "unknown"
    at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auth_failure_source ON auth_failure (source, at);
CREATE INDEX auth_failure_at ON auth_failure (at);  -- the sweep of old rows
