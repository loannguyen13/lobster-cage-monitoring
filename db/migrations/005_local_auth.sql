-- Application accounts, distinct from PostgreSQL login roles. No default password.
BEGIN;
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9_.-]{3,64}$'),
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('Viewer','Operator','Admin')),
    enabled BOOLEAN NOT NULL DEFAULT true,
    failed_attempts INT NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS auth_sessions_user_idx ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS auth_sessions_expiry_idx ON auth_sessions(expires_at);
COMMIT;
