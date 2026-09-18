CREATE TABLE users (
    id uuid PRIMARY KEY,
    login varchar(256) NOT NULL,
    role varchar(256) NOT NULL,
    is_active boolean NOT NULL,
    CONSTRAINT users_login_not_blank CHECK (btrim(login) <> ''),
    CONSTRAINT users_role_not_blank CHECK (btrim(role) <> '')
);

CREATE TABLE refresh_tokens (
    id uuid PRIMARY KEY,
    family_id uuid NOT NULL,
    user_id uuid NOT NULL REFERENCES users (id),
    token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    revoked_at timestamptz,
    CONSTRAINT refresh_tokens_sha256_hash_length CHECK (octet_length(token_hash) = 32),
    CONSTRAINT refresh_tokens_valid_lifetime CHECK (expires_at > created_at)
);

CREATE INDEX idx_refresh_tokens_family ON refresh_tokens (family_id);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens (user_id);
CREATE UNIQUE INDEX uq_refresh_tokens_active_family ON refresh_tokens (family_id)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;
