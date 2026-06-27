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

-- ROLLBACK
-- DROP INDEX IF EXISTS idx_evaluation_records_user_id;
-- DROP INDEX IF EXISTS idx_reward_model_records_user_id_created;
-- DROP INDEX IF EXISTS idx_narration_variants_session_id_style;
-- DROP INDEX IF EXISTS idx_feedback_events_session_id_created;
-- DROP INDEX IF EXISTS idx_feedback_events_user_id_created;
