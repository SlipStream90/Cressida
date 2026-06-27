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

-- ROLLBACK
-- DROP TABLE IF EXISTS evaluation_records CASCADE;
