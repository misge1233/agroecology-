from fastapi import APIRouter

from app.metadata_service import build_metadata
from app.schemas import MetadataResponse

router = APIRouter(tags=["metadata"])


@router.get("/metadata", response_model=MetadataResponse)
def metadata():
    return build_metadata()
