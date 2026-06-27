from datetime import datetime
from typing import Optional


class DriftReport:
    def __init__(
        self,
        user_id: str,
        previous_dominant_style: str,
        emerging_dominant_style: str,
        drift_confidence: float,
        sessions_analyzed: int,
        recommendation: str,
        detected_at: Optional[str] = None,
    ):
        self.user_id = user_id
        self.detected_at = detected_at or datetime.now().isoformat()
        self.previous_dominant_style = previous_dominant_style
        self.emerging_dominant_style = emerging_dominant_style
        self.drift_confidence = drift_confidence
        self.sessions_analyzed = sessions_analyzed
        self.recommendation = recommendation

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "detected_at": self.detected_at,
            "previous_dominant_style": self.previous_dominant_style,
            "emerging_dominant_style": self.emerging_dominant_style,
            "drift_confidence": self.drift_confidence,
            "sessions_analyzed": self.sessions_analyzed,
            "recommendation": self.recommendation,
        }


_reward_records: list[dict] = []
_drift_reports: list[DriftReport] = []


def compute_style_trajectory(
    user_id: str,
    lookback_sessions: int = 10,
) -> dict[str, list[float]]:
    records = [r for r in _reward_records if r.get("user_id") == user_id]
    records = records[-lookback_sessions:]

    trajectory: dict[str, list[float]] = {
        "suspense": [],
        "dialogue": [],
        "emotional": [],
        "fast_paced": [],
        "descriptive": [],
    }
    for record in records:
        scores = record.get("updated_style_scores", {})
        for style in trajectory:
            trajectory[style].append(scores.get(style, 0.2))
    return trajectory


def detect_drift(
    user_id: str,
    lookback_sessions: int = 10,
) -> Optional[DriftReport]:
    trajectory = compute_style_trajectory(user_id, lookback_sessions)
    n = len(next(iter(trajectory.values())))
    if n < 3:
        return None

    slopes: dict[str, float] = {}
    for style, values in trajectory.items():
        if len(values) < 2:
            slopes[style] = 0.0
            continue
        x1, y1 = 0, values[0]
        x2, y2 = len(values) - 1, values[-1]
        run = x2 - x1
        slopes[style] = (y2 - y1) / run if run else 0.0

    previous_dominant = max(trajectory, key=lambda s: trajectory[s][0])
    emerging_dominant = max(slopes, key=slopes.get)

    if emerging_dominant == previous_dominant:
        return None

    slope = slopes[emerging_dominant]
    if slope <= 0.02:
        return None

    drift_confidence = min(1.0, slope / 0.05)
    recommendation = "accelerate" if drift_confidence > 0.7 else "monitor"

    report = DriftReport(
        user_id=user_id,
        previous_dominant_style=previous_dominant,
        emerging_dominant_style=emerging_dominant,
        drift_confidence=drift_confidence,
        sessions_analyzed=n,
        recommendation=recommendation,
    )
    _drift_reports.append(report)
    return report


def apply_drift_acceleration(user_id: str, drift_report: DriftReport) -> None:
    if drift_report.drift_confidence > 0.7:
        record = {
            "user_id": user_id,
            "source": "drift_acceleration",
            "emerging_style": drift_report.emerging_dominant_style,
            "boost_applied": 0.10,
            "timestamp": datetime.now().isoformat(),
        }
        _reward_records.append({
            "user_id": user_id,
            "updated_style_scores": {
                drift_report.emerging_dominant_style: 0.10,
            },
            "source": "drift_acceleration",
        })
