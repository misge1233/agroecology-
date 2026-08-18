from fastapi import APIRouter

from app.schemas import ModelListItem
from app.services import recommender_service as svc

router = APIRouter(tags=["models"])

_FEATURES = [
    "CSA_practices",
    "practice_family",
    "Crop_group",
    "crop_type",
    "aez_belt",
    "Indicator",
    "land_cover",
    "Rainfall",
    "Altitude_r",
    "temp_mean_annual",
    "precip_seasonality",
    "slope",
    "soil_clay",
]


@router.get("/models", response_model=list[ModelListItem])
def models():
    """Single current model — the pooled RandomForest CSA response-ratio ranker."""
    return [
        ModelListItem(
            key="csa_agroecology",
            label="CSA Agroecology (Ethiopia)",
            description=(
                "Pooled RandomForest predicting the with/without response ratio of "
                "Climate-Smart Agriculture practices from a map location (auto-derived "
                "agro-ecological context), practice family, and goal indicator."
            ),
            features=_FEATURES,
        )
    ]
