from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from routers.auth import get_current_user
from services.ml_model import train_all_models, get_model_status

router = APIRouter(prefix="/api/ml", tags=["ml"])


@router.post("/train")
def train_models(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Train all machine-material regression models from database data."""
    results = train_all_models(db)
    return {"results": results}


@router.get("/status")
def model_status(
    current_user: User = Depends(get_current_user)
):
    """Return training status for all 8 machine-material models."""
    return {"models": get_model_status()}
