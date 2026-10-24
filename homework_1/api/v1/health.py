from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    return JSONResponse(
        status_code=status.HTTP_200_OK, content={"status": "ok"}
    )
