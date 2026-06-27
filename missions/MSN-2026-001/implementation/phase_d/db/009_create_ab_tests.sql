CREATE TABLE IF NOT EXISTS ab_test_configs (
    test_id             TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    styles_under_test   JSONB NOT NULL DEFAULT '[]',
    assignment_strategy TEXT NOT NULL DEFAULT 'round_robin',
    active              BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ab_test_results (
    id                SERIAL PRIMARY KEY,
    test_id           TEXT NOT NULL REFERENCES ab_test_configs(test_id),
    user_id           TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    segment_id        TEXT NOT NULL,
    assigned_style    TEXT NOT NULL,
    variant_id        TEXT NOT NULL,
    explicit_rating   FLOAT,
    implicit_signals  JSONB DEFAULT '[]',
    completion        BOOLEAN DEFAULT false,
    engagement_score  FLOAT DEFAULT 0.0,
    recorded_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ab_results_test_id ON ab_test_results(test_id);
CREATE INDEX IF NOT EXISTS idx_ab_results_user_id ON ab_test_results(user_id);
CREATE INDEX IF NOT EXISTS idx_ab_results_session_id ON ab_test_results(session_id);
CREATE INDEX IF NOT EXISTS idx_ab_results_assigned_style ON ab_test_results(assigned_style);
