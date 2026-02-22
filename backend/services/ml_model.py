import os
import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
from models import Inquiry

MODEL_PATH_PRICE = "models/price_model.pkl"
MODEL_PATH_TIME = "models/time_model.pkl"
os.makedirs("models", exist_ok=True)

FEATURES = [
    "quantity",
    "part_volume_cm3",
    "stock_percent",
    "support_volume_percent",
    "part_height_mm",
    "prep_time_h",
    "post_handling_time_h",
    "blasting_time_h",
    "leak_testing_time_h",
    "qc_time_h",
    "projected_xy_surface_cm2"
]


def _inquiries_to_dataframe(inquiries: list) -> pd.DataFrame:
    rows = []
    for inq in inquiries:
        rows.append({
            "quantity": inq.quantity or 1,
            "part_volume_cm3": float(inq.part_volume_cm3 or 0),
            "stock_percent": float(inq.stock_percent or 0),
            "support_volume_percent": float(inq.support_volume_percent or 0),
            "part_height_mm": float(inq.part_height_mm or 0),
            "prep_time_h": float(inq.prep_time_h or 0),
            "post_handling_time_h": float(inq.post_handling_time_h or 0),
            "blasting_time_h": float(inq.blasting_time_h or 0),
            "leak_testing_time_h": float(inq.leak_testing_time_h or 0),
            "qc_time_h": float(inq.qc_time_h or 0),
            "projected_xy_surface_cm2": float(inq.projected_xy_surface_cm2 or 0),
            "estimated_part_price_eur": float(inq.estimated_part_price_eur or 0),
            "estimated_build_time_h": float(inq.estimated_build_time_h or 0),
        })
    return pd.DataFrame(rows)


def train_models(db: Session) -> dict:
    """
    Trains price and build time regression models on all inquiries
    that have estimated values (used as ground truth from company template).
    Requires at least 10 records to train.
    """
    inquiries = db.query(Inquiry).filter(
        Inquiry.estimated_part_price_eur != None,
        Inquiry.estimated_build_time_h != None
    ).all()

    if len(inquiries) < 10:
        return {
            "success": False,
            "message": f"Zu wenig Daten zum Trainieren. Mindestens 10 Datensätze benötigt, aktuell: {len(inquiries)}"
        }

    df = _inquiries_to_dataframe(inquiries)
    X = df[FEATURES].fillna(0)

    # Train price model
    y_price = df["estimated_part_price_eur"]
    X_train, X_test, y_train, y_test = train_test_split(X, y_price, test_size=0.2, random_state=42)
    price_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model", GradientBoostingRegressor(n_estimators=100, random_state=42))
    ])
    price_pipeline.fit(X_train, y_train)
    price_mae = mean_absolute_error(y_test, price_pipeline.predict(X_test))
    joblib.dump(price_pipeline, MODEL_PATH_PRICE)

    # Train build time model
    y_time = df["estimated_build_time_h"]
    X_train, X_test, y_train, y_test = train_test_split(X, y_time, test_size=0.2, random_state=42)
    time_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model", GradientBoostingRegressor(n_estimators=100, random_state=42))
    ])
    time_pipeline.fit(X_train, y_train)
    time_mae = mean_absolute_error(y_test, time_pipeline.predict(X_test))
    joblib.dump(time_pipeline, MODEL_PATH_TIME)

    return {
        "success": True,
        "training_samples": len(inquiries),
        "price_model_mae_eur": round(price_mae, 2),
        "time_model_mae_h": round(time_mae, 2),
        "message": f"Modelle erfolgreich trainiert mit {len(inquiries)} Datensätzen."
    }


def predict(inquiry_data: dict) -> dict:
    """
    Predicts part price and build time for a new inquiry using trained models.
    Falls back to None if models are not yet trained.
    """
    if not os.path.exists(MODEL_PATH_PRICE) or not os.path.exists(MODEL_PATH_TIME):
        return {
            "estimated_part_price_eur": None,
            "estimated_build_time_h": None,
            "message": "Modelle noch nicht trainiert. Bitte zuerst das Training starten."
        }

    price_model = joblib.load(MODEL_PATH_PRICE)
    time_model = joblib.load(MODEL_PATH_TIME)

    features = pd.DataFrame([{
        "quantity": inquiry_data.get("quantity", 1),
        "part_volume_cm3": inquiry_data.get("part_volume_cm3", 0),
        "stock_percent": inquiry_data.get("stock_percent", 0),
        "support_volume_percent": inquiry_data.get("support_volume_percent", 0),
        "part_height_mm": inquiry_data.get("part_height_mm", 0),
        "prep_time_h": inquiry_data.get("prep_time_h", 0),
        "post_handling_time_h": inquiry_data.get("post_handling_time_h", 0),
        "blasting_time_h": inquiry_data.get("blasting_time_h", 0),
        "leak_testing_time_h": inquiry_data.get("leak_testing_time_h", 0),
        "qc_time_h": inquiry_data.get("qc_time_h", 0),
        "projected_xy_surface_cm2": inquiry_data.get("projected_xy_surface_cm2", 0),
    }])

    predicted_price = float(price_model.predict(features)[0])
    predicted_time = float(time_model.predict(features)[0])

    return {
        "estimated_part_price_eur": round(max(predicted_price, 0), 2),
        "estimated_build_time_h": round(max(predicted_time, 0), 2),
        "message": "Schätzung erfolgreich"
    }
