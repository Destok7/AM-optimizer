import os
import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

os.makedirs("models", exist_ok=True)

# 8 machine-material model keys
MODEL_KEYS = [
    "Xline_AlSi10Mg",
    "EOS_AlSi10Mg",
    "EOS_IN718_IN625",
    "M2_alt_IN718_IN625",
    "M2_alt_1.4404",
    "M2_neu_AlSi10Mg",
    "M2_neu_IN718_IN625",
    "M2_neu_1.4404",
]

# Regression input features
FEATURES = [
    "quantity",
    "part_volume_mm3",
    "stock_cm3",
    "support_volume_cm3",
    "part_height_mm",
    "prep_time_min",
    "post_handling_time_min",
    "blasting_time_min",
    "leak_testing_time_min",
    "qc_time_min",
]


def get_model_key(machine: str, material: str) -> str:
    """Returns the model key for a given machine-material combination."""
    mat_group = "IN718_IN625" if material in ("IN718", "IN625") else material
    return f"{machine}_{mat_group}"


def model_path(key: str, target: str) -> str:
    """Returns file path for a model. target = 'price' or 'time'"""
    safe_key = key.replace(".", "_").replace(" ", "_")
    return f"models/{safe_key}_{target}.pkl"


def model_exists(key: str) -> bool:
    return (
        os.path.exists(model_path(key, "price")) and
        os.path.exists(model_path(key, "time"))
    )


def _build_pipeline(n_samples: int):
    """Use GradientBoosting for larger datasets, LinearRegression for small ones."""
    if n_samples >= 30:
        return Pipeline([
            ("scaler", StandardScaler()),
            ("model", GradientBoostingRegressor(n_estimators=100, random_state=42))
        ])
    else:
        return Pipeline([
            ("scaler", StandardScaler()),
            ("model", LinearRegression())
        ])


def train_model_for_key(key: str, df: pd.DataFrame) -> dict:
    """Train price and time models for a specific machine-material key."""
    if len(df) < 5:
        return {
            "success": False,
            "key": key,
            "message": f"Zu wenig Daten ({len(df)} Datensätze). Mindestens 5 benötigt."
        }

    X = df[FEATURES].fillna(0)
    y_price = df["manual_part_price_eur"].fillna(0)
    y_time  = df["manual_build_time_h"].fillna(0)

    # Price model
    price_pipeline = _build_pipeline(len(df))
    if len(df) >= 10:
        X_tr, X_te, y_tr, y_te = train_test_split(X, y_price, test_size=0.2, random_state=42)
        price_pipeline.fit(X_tr, y_tr)
        price_mae = mean_absolute_error(y_te, price_pipeline.predict(X_te))
    else:
        price_pipeline.fit(X, y_price)
        price_mae = mean_absolute_error(y_price, price_pipeline.predict(X))

    joblib.dump(price_pipeline, model_path(key, "price"))

    # Time model
    time_pipeline = _build_pipeline(len(df))
    if len(df) >= 10:
        X_tr, X_te, y_tr, y_te = train_test_split(X, y_time, test_size=0.2, random_state=42)
        time_pipeline.fit(X_tr, y_tr)
        time_mae = mean_absolute_error(y_te, time_pipeline.predict(X_te))
    else:
        time_pipeline.fit(X, y_time)
        time_mae = mean_absolute_error(y_time, time_pipeline.predict(X))

    joblib.dump(time_pipeline, model_path(key, "time"))

    return {
        "success": True,
        "key": key,
        "samples": len(df),
        "price_mae_eur": round(price_mae, 2),
        "time_mae_h": round(time_mae, 4),
        "message": f"Modell '{key}' trainiert mit {len(df)} Datensätzen."
    }


def train_all_models(db: Session) -> list:
    """Train all 8 machine-material models from database data."""
    from models import Part, Inquiry

    # Load all parts with inquiry data
    rows = (
        db.query(Part, Inquiry)
        .join(Inquiry, Part.inquiry_id == Inquiry.inquiry_id)
        .filter(
            Part.manual_part_price_eur != None,
            Part.manual_build_time_h != None
        )
        .all()
    )

    if not rows:
        return [{"success": False, "message": "Keine Daten mit manuellen Preisen gefunden."}]

    # Build dataframe
    records = []
    for part, inquiry in rows:
        mat_group = "IN718_IN625" if part.material in ("IN718", "IN625") else part.material
        records.append({
            "model_key":             f"{inquiry.machine}_{mat_group}",
            "quantity":              part.quantity or 1,
            "part_volume_mm3":       float(part.part_volume_mm3 or 0),
            "stock_cm3":             float(part.stock_cm3 or 0),
            "support_volume_cm3":    float(part.support_volume_cm3 or 0),
            "part_height_mm":        float(part.part_height_mm or 0),
            "prep_time_min":         float(part.prep_time_min or 0),
            "post_handling_time_min":float(part.post_handling_time_min or 0),
            "blasting_time_min":     float(part.blasting_time_min or 0),
            "leak_testing_time_min": float(part.leak_testing_time_min or 0),
            "qc_time_min":           float(part.qc_time_min or 0),
            "manual_part_price_eur": float(part.manual_part_price_eur or 0),
            "manual_build_time_h":   float(part.manual_build_time_h or 0),
        })

    df = pd.DataFrame(records)
    results = []

    for key in MODEL_KEYS:
        subset = df[df["model_key"] == key]
        result = train_model_for_key(key, subset)
        results.append(result)

    return results


def predict(machine: str, material: str, part_data: dict) -> dict:
    """Predict part price and build time for given machine-material and part parameters."""
    key = get_model_key(machine, material)

    if not model_exists(key):
        return {
            "calc_part_price_eur": None,
            "calc_build_time_h": None,
            "model_key": key,
            "message": f"Modell '{key}' noch nicht trainiert."
        }

    price_model = joblib.load(model_path(key, "price"))
    time_model  = joblib.load(model_path(key, "time"))

    features = pd.DataFrame([{
        "quantity":              part_data.get("quantity", 1),
        "part_volume_mm3":       part_data.get("part_volume_mm3", 0),
        "stock_cm3":             part_data.get("stock_cm3", 0),
        "support_volume_cm3":    part_data.get("support_volume_cm3", 0),
        "part_height_mm":        part_data.get("part_height_mm", 0),
        "prep_time_min":         part_data.get("prep_time_min", 0),
        "post_handling_time_min":part_data.get("post_handling_time_min", 0),
        "blasting_time_min":     part_data.get("blasting_time_min", 0),
        "leak_testing_time_min": part_data.get("leak_testing_time_min", 0),
        "qc_time_min":           part_data.get("qc_time_min", 0),
    }])

    predicted_price = float(price_model.predict(features)[0])
    predicted_time  = float(time_model.predict(features)[0])

    return {
        "calc_part_price_eur": round(max(predicted_price, 0), 2),
        "calc_build_time_h":   round(max(predicted_time, 0), 4),
        "model_key":           key,
        "message":             "Schätzung erfolgreich"
    }


def get_model_status() -> list:
    """Returns training status for all 8 models."""
    status = []
    for key in MODEL_KEYS:
        exists = model_exists(key)
        status.append({
            "model_key": key,
            "trained": exists,
            "price_model": model_path(key, "price") if exists else None,
            "time_model":  model_path(key, "time") if exists else None,
        })
    return status
