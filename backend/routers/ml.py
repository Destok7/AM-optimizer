from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import User
from routers.auth import get_current_user
from services.ml_model import train_models, predict

router = APIRouter(prefix="/api/ml", tags=["ml"])


class PredictRequest(BaseModel):
    quantity: int
    part_volume_cm3: float
    stock_percent: Optional[float] = 0
    support_volume_percent: float
    part_height_mm: float
    prep_time_h: Optional[float] = 0
    post_handling_time_h: Optional[float] = 0
    blasting_time_h: Optional[float] = 0
    leak_testing_time_h: Optional[float] = 0
    qc_time_h: Optional[float] = 0
    projected_xy_surface_cm2: Optional[float] = 0


@router.post("/train")
def trigger_training(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = train_models(db)
    return result


@router.post("/predict")
def predict_price_and_time(
    data: PredictRequest,
    current_user: User = Depends(get_current_user)
):
    result = predict(data.dict())
    return result
