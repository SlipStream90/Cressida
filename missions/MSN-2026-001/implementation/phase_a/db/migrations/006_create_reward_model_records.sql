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

-- ROLLBACK
-- DROP TABLE IF EXISTS reward_model_records CASCADE;
