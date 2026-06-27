CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    display_name TEXT,
    embedding vector(768),
    style_scores JSONB NOT NULL DEFAULT '{"suspense":0.2,"dialogue":0.2,"emotional":0.2,"fast_paced":0.2,"descriptive":0.2}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own" ON users FOR SELECT USING (id = auth.uid());
CREATE POLICY "users_insert_own" ON users FOR INSERT WITH CHECK (id = auth.uid());
CREATE POLICY "users_update_own" ON users FOR UPDATE USING (id = auth.uid());

CREATE INDEX idx_users_username ON users (username);

-- ROLLBACK
-- DROP TABLE IF EXISTS users CASCADE;
