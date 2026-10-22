-- What the check job found at an address (plan M1, 2.5; Gesamtplan §7.5): one row per address,
-- whichever entries hold it. The content was streamed and hashed, never stored. Kept under the
-- address's SHA-256: 2000 signs may pass what one B-tree entry holds (0006_sources).
CREATE TABLE url_check (
    url_sha256 bytea PRIMARY KEY CHECK (url_sha256 = sha256(convert_to(url, 'UTF8'))),
    url text NOT NULL CHECK (url ~ '^https?://' AND length(url) <= 2000),
    outcome text NOT NULL CHECK (outcome IN (
        'reachable', 'too_large', 'refused', 'throttled', 'server_error', 'unavailable', 'unreachable',
        'robots'
    )),
    status_code smallint CHECK (status_code BETWEEN 100 AND 599),  -- of the last answer, if one came
    final_url text CHECK (final_url ~ '^https?://' AND length(final_url) <= 2000),  -- after redirects
    content_type text CHECK (length(content_type) <= 200),  -- as the server said it
    detected_type text CHECK (detected_type IN ('pdf', 'docx', 'rtf', 'html', 'other')),
    size_bytes bigint CHECK (size_bytes >= 0),
    sha256 bytea CHECK (length(sha256) = 32),
    last_modified text CHECK (length(last_modified) <= 100),  -- the server's Last-Modified, as sent
    checked_at timestamptz NOT NULL DEFAULT now(),
    -- a body read to its end has a hash and a size, and only a reachable address's is
    CHECK ((sha256 IS NULL) = (size_bytes IS NULL)),
    CHECK ((outcome = 'reachable') = (sha256 IS NOT NULL))
);

-- When each host may next be asked: one request per CHECK_HOST_INTERVAL_S, across all workers
CREATE TABLE host_throttle (
    host text PRIMARY KEY CHECK (length(host) BETWEEN 1 AND 253),  -- as DNS holds a name
    next_at timestamptz NOT NULL
);
