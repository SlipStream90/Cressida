from fastapi import APIRouter, Depends, Query

from app.api.deps import verify_api_key
from app.core.config import settings
from app.services.drift_service import compute_style_trajectory, detect_drift
from app.services.ab_service import _stores

router = APIRouter(prefix=f"{settings.api_prefix}/analytics", tags=["analytics"])


@router.get("/users/{user_id}/style-history")
async def get_style_history(
    user_id: str,
    sessions: int = Query(20, ge=1, le=100),
    api_key: str = Depends(verify_api_key),
):
    trajectory = compute_style_trajectory(user_id, lookback_sessions=sessions)
    return {
        "user_id": user_id,
        "sessions_analyzed": len(next(iter(trajectory.values()))) if trajectory else 0,
        "trajectory": trajectory,
    }


@router.get("/users/{user_id}/drift")
async def get_drift_report(
    user_id: str,
    api_key: str = Depends(verify_api_key),
):
    report = detect_drift(user_id)
    if report:
        return report.to_dict()
    return {"user_id": user_id, "drift_detected": False}


@router.get("/users/{user_id}/session-summary")
async def get_session_summary(
    user_id: str,
    api_key: str = Depends(verify_api_key),
):
    results = [r for r in _stores.get("ab_results", []) if r.user_id == user_id]
    sessions: dict[str, dict] = {}
    for r in results:
        if r.session_id not in sessions:
            sessions[r.session_id] = {
                "session_id": r.session_id,
                "dominant_style": r.assigned_style,
                "signals_received": 0,
                "completion_rate": 0.0,
                "engagement_score": 0.0,
                "segment_count": 0,
            }
        s = sessions[r.session_id]
        s["segment_count"] += 1
        s["signals_received"] += len(r.implicit_signals)
        s["engagement_score"] = max(s["engagement_score"], r.engagement_score)
        if r.completion:
            s["completion_rate"] = (
                s.get("_completions", 0) + 1
            ) / s["segment_count"]
            s["_completions"] = s.get("_completions", 0) + 1

    return {
        "user_id": user_id,
        "sessions": list(sessions.values()),
    }
