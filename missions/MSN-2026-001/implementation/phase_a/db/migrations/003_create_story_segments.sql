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

-- ROLLBACK
-- DROP TABLE IF EXISTS story_segments CASCADE;
