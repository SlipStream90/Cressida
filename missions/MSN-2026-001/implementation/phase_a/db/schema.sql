-- ECHO — Consolidated Schema
-- Combines all 8 migrations in dependency order for clean installs.

-- 001
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

-- 002
CREATE TABLE style_presets (
    style_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    system_prompt TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE style_presets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "style_presets_select_all" ON style_presets FOR SELECT USING (true);
CREATE POLICY "style_presets_insert_admin" ON style_presets FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "style_presets_update_admin" ON style_presets FOR UPDATE USING (auth.role() = 'service_role');
CREATE POLICY "style_presets_delete_admin" ON style_presets FOR DELETE USING (auth.role() = 'service_role');

CREATE INDEX idx_style_presets_name ON style_presets (name);

INSERT INTO style_presets (name, description, system_prompt) VALUES
    ('suspense', 'Short sentences, rising tension, dramatic pauses',
     'You are a suspense narrator. Use short, punchy sentences. Build tension gradually. Use dramatic pauses indicated by ellipses. Keep descriptions atmospheric but sparse. Focus on what is felt rather than what is seen. End sentences with impact.'),
    ('dialogue', 'Heavy dialogue, minimal description, quick exchanges',
     'You are a dialogue-focused narrator. Prioritize character conversations over description. Use quick exchanges, interruptions, and natural speech patterns. Keep narration minimal — only enough to establish who is speaking and the setting.'),
    ('emotional', 'Rich emotional language, internal monologue',
     'You are an emotionally resonant narrator. Use rich, evocative language that connects to the listener''s emotions. Include internal monologue and sensory details. Describe feelings, reactions, and the emotional weight of each moment.'),
    ('fast_paced', 'Quick narration, minimal description, action-forward',
     'You are a fast-paced action narrator. Keep sentences short and driving. Minimize description — focus on actions and events. Use active voice. Maintain momentum. Every sentence should advance the scene.'),
    ('descriptive', 'Detailed atmospheric description, slower pace',
     'You are an atmospheric narrator. Use rich, detailed descriptions of settings, characters, and moods. Take your time building the world. Paint vivid pictures with words. Let the listener feel immersed in every scene.');

-- 003
CREATE TABLE story_segments (
    segment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE story_segments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "story_segments_select_all" ON story_segments FOR SELECT USING (true);
CREATE POLICY "story_segments_insert_service" ON story_segments FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "story_segments_update_service" ON story_segments FOR UPDATE USING (auth.role() = 'service_role');
CREATE POLICY "story_segments_delete_service" ON story_segments FOR DELETE USING (auth.role() = 'service_role');

CREATE INDEX idx_story_segments_created_at ON story_segments (created_at DESC);

-- 004
CREATE TABLE narration_variants (
    variant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    segment_id UUID NOT NULL REFERENCES story_segments(segment_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    style_name TEXT NOT NULL REFERENCES style_presets(name) ON DELETE RESTRICT,
    narrative_text TEXT NOT NULL,
    audio_url TEXT,
    audio_duration_ms INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE narration_variants ENABLE ROW LEVEL SECURITY;

CREATE POLICY "narration_variants_select_own" ON narration_variants
    FOR SELECT USING (auth.role() = 'service_role' OR true);
CREATE POLICY "narration_variants_insert_service" ON narration_variants
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE INDEX idx_narration_variants_session_id ON narration_variants (session_id);
CREATE INDEX idx_narration_variants_style_name ON narration_variants (style_name);

-- 005
CREATE TABLE feedback_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    segment_id UUID REFERENCES story_segments(segment_id) ON DELETE SET NULL,
    variant_id UUID REFERENCES narration_variants(variant_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    signal_type TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE feedback_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "feedback_events_select_own" ON feedback_events FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "feedback_events_insert_own" ON feedback_events FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE INDEX idx_feedback_events_user_id ON feedback_events (user_id);
CREATE INDEX idx_feedback_events_session_id ON feedback_events (session_id);
CREATE INDEX idx_feedback_events_created_at ON feedback_events (created_at DESC);

-- 006
CREATE TABLE reward_model_records (
    record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    variant_id UUID REFERENCES narration_variants(variant_id) ON DELETE SET NULL,
    style_scores_before JSONB NOT NULL,
    style_scores_after JSONB NOT NULL,
    selected_style TEXT NOT NULL,
    signals JSONB NOT NULL DEFAULT '[]',
    model_version TEXT NOT NULL DEFAULT 'weighted-scoring-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE reward_model_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "reward_model_records_select_own" ON reward_model_records
    FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "reward_model_records_insert_service" ON reward_model_records
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE INDEX idx_reward_model_records_user_id ON reward_model_records (user_id);

-- 007
CREATE TABLE evaluation_records (
    eval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    segment_id UUID REFERENCES story_segments(segment_id) ON DELETE SET NULL,
    variant_id UUID REFERENCES narration_variants(variant_id) ON DELETE SET NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    feedback TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE evaluation_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "evaluation_records_select_own" ON evaluation_records FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "evaluation_records_insert_own" ON evaluation_records FOR INSERT WITH CHECK (user_id = auth.uid());

-- 008
CREATE INDEX IF NOT EXISTS idx_feedback_events_user_id_created
    ON feedback_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_events_session_id_created
    ON feedback_events (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_narration_variants_session_id_style
    ON narration_variants (session_id, style_name);
CREATE INDEX IF NOT EXISTS idx_reward_model_records_user_id_created
    ON reward_model_records (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluation_records_user_id
    ON evaluation_records (user_id);
