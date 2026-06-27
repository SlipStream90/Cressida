from typing import Annotated

from fastapi import Header, HTTPException, status

API_KEY_HEADER = "X-API-Key"


async def verify_api_key(x_api_key: Annotated[str, Header(alias=API_KEY_HEADER)] = "") -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    return x_api_key
