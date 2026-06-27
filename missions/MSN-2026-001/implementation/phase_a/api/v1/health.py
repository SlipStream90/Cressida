from datetime import datetime

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "name": settings.app_name,
        "version": settings.app_version,
        "uptime": datetime.now().isoformat(),
    }
