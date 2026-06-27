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

-- ROLLBACK
-- DROP TABLE IF EXISTS feedback_events CASCADE;
