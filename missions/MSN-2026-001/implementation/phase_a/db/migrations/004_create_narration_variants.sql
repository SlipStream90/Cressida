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

-- ROLLBACK
-- DROP TABLE IF EXISTS narration_variants CASCADE;
