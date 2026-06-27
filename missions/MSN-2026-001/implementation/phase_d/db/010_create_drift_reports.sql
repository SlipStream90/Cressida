CREATE TABLE IF NOT EXISTS drift_reports (
    id                        SERIAL PRIMARY KEY,
    user_id                   TEXT NOT NULL,
    detected_at               TIMESTAMPTZ DEFAULT NOW(),
    previous_dominant_style   TEXT NOT NULL,
    emerging_dominant_style   TEXT NOT NULL,
    drift_confidence          FLOAT NOT NULL,
    sessions_analyzed         INT NOT NULL,
    recommendation            TEXT NOT NULL,
    boost_applied             FLOAT DEFAULT 0.0,
    created_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drift_reports_user_id ON drift_reports(user_id);
CREATE INDEX IF NOT EXISTS idx_drift_reports_detected_at ON drift_reports(detected_at);
