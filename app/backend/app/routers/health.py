from fastapi import APIRouter

from app import __version__
from app.schemas import HealthResponse
from app.services import recommender_service as svc

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok" if svc.is_ready() else "starting",
        model_loaded=svc.is_ready(),
        version=__version__,
    )
