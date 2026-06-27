import uuid
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.deps import verify_api_key
from app.core.config import settings
from .ab_service import (
    ABTestConfig,
    get_ab_assignment,
    record_ab_result,
    update_ab_result_with_feedback,
    get_ab_results_summary,
    _stores,
)

router = APIRouter(prefix=f"{settings.api_prefix}/abtests", tags=["abtests"])


@router.post("")
async def create_ab_test(
    name: str,
    styles_under_test: list[str],
    assignment_strategy: str = "round_robin",
    api_key: str = Depends(verify_api_key),
):
    config = ABTestConfig(
        test_id=str(uuid.uuid4()),
        name=name,
        styles_under_test=styles_under_test,
        assignment_strategy=assignment_strategy,
    )
    _stores.setdefault("ab_configs", []).append(config)
    return config.to_dict()


@router.get("/{test_id}")
async def get_ab_test(test_id: str, api_key: str = Depends(verify_api_key)):
    for c in _stores.get("ab_configs", []):
        if c.test_id == test_id:
            return c.to_dict()
    return {"error": "not_found"}


@router.get("/{test_id}/results")
async def get_ab_results(test_id: str, api_key: str = Depends(verify_api_key)):
    return get_ab_results_summary(test_id)


@router.get("/{test_id}/results/raw")
async def get_ab_results_raw(test_id: str, api_key: str = Depends(verify_api_key)):
    results = _stores.get("ab_results", [])
    return [r.to_dict() for r in results if r.test_id == test_id]


@router.patch("/{test_id}/active")
async def toggle_ab_test(
    test_id: str,
    active: bool,
    api_key: str = Depends(verify_api_key),
):
    for c in _stores.get("ab_configs", []):
        if c.test_id == test_id:
            c.active = active
            return {"test_id": test_id, "active": active}
    return {"error": "not_found"}
