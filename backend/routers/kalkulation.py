from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from pydantic import BaseModel
from datetime import date
import datetime

from database import get_db
from models import (
    CombinedCalculation, CalcPart, Part, Inquiry,
    User, MACHINE_MATERIALS, MACHINE_PLATFORM_MM2, get_material_group
)
from routers.auth import get_current_user
from services.ml_model import predict

router = APIRouter(prefix="/api/kalkulation", tags=["kalkulation"])


class CalcCreate(BaseModel):
    calc_name: str
    machine: str
    material_group: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class CalcUpdate(BaseModel):
    calc_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None


class AddPartsRequest(BaseModel):
    part_ids: List[int]
    inquiry_id: Optional[int] = None


class CalcPartUpdate(BaseModel):
    material_override: Optional[str] = None
    quantity_override: Optional[int] = None
    part_volume_cm3: Optional[float] = None
    aufmass_pct: Optional[float] = None
    support_volume_cm3: Optional[float] = None
    part_height_mm: Optional[float] = None
    prep_time_min: Optional[float] = None
    post_handling_time_min: Optional[float] = None
    blasting_time_min: Optional[float] = None
    leak_testing_time_min: Optional[float] = None
    qc_time_min: Optional[float] = None


def generate_calc_number() -> str:
    now = datetime.datetime.now()
    return f"CALC-{now.strftime('%Y%m%d-%H%M%S')}"


def calc_platform_percent(calc: CombinedCalculation, db: Session) -> float:
    platform = float(calc.platform_surface_mm2 or 0)
    if platform == 0:
        return 0
    total = 0
    for cp in calc.calc_parts:
        part = db.query(Part).filter(Part.part_id == cp.part_id).first()
        if part and part.projected_xy_surface_mm2:
            qty = cp.quantity_override or part.quantity
            total += float(part.projected_xy_surface_mm2) * qty
    return round(total / platform * 100, 1)


def get_part_data_for_predict(part: Part, cp: CalcPart) -> dict:
    """Merge part data with any calc-level overrides for regression input."""
    return {
        "quantity":               cp.quantity_override or part.quantity,
        "part_volume_cm3":        float(cp.part_volume_cm3_override or part.part_volume_cm3 or 0),
        "aufmass_pct":              float(cp.aufmass_pct_override or part.aufmass_pct or 0),
        "support_volume_cm3":     float(cp.support_volume_cm3_override or part.support_volume_cm3 or 0),
        "part_height_mm":         float(cp.part_height_mm_override or part.part_height_mm or 0),
        "prep_time_min":          float(cp.prep_time_min_override or part.prep_time_min or 0),
        "post_handling_time_min": float(cp.post_handling_time_min_override or part.post_handling_time_min or 0),
        "blasting_time_min":      float(cp.blasting_time_min_override or part.blasting_time_min or 0),
        "leak_testing_time_min":  float(cp.leak_testing_time_min_override or part.leak_testing_time_min or 0),
        "qc_time_min":            float(cp.qc_time_min_override or part.qc_time_min or 0),
    }


def serialize_calc(calc: CombinedCalculation, db: Session) -> dict:
    platform_pct = calc_platform_percent(calc, db)
    parts_data = []
    total_manual_price = 0
    total_calc_price = 0

    for cp in calc.calc_parts:
        part = db.query(Part).filter(Part.part_id == cp.part_id).first()
        inq = db.query(Inquiry).filter(Inquiry.inquiry_id == part.inquiry_id).first() if part else None
        if not part:
            continue

        qty = cp.quantity_override or part.quantity
        material = cp.material_override or part.material
        manual_price = float(part.manual_part_price_eur or 0) * qty
        calc_price = float(cp.calc_part_price_eur or 0) * qty if cp.calc_part_price_eur else None
        savings_eur = round(manual_price - calc_price, 2) if calc_price is not None else None
        savings_pct = round((manual_price - calc_price) / manual_price * 100, 1) if calc_price and manual_price else None

        total_manual_price += manual_price
        if calc_price:
            total_calc_price += calc_price

        parts_data.append({
            "cp_id":                      cp.id,
            "part_id":                    part.part_id,
            "inquiry_id":                 part.inquiry_id,
            "inquiry_number":             inq.inquiry_number if inq else None,
            "order_number":               inq.order_number if inq else None,
            "customer_number":            inq.customer_number if inq else None,
            "manual_build_time_h":        float(inq.manual_build_time_h) if inq and inq.manual_build_time_h else None,
            "material":                   material,
            "part_name":                  part.part_name,
            "quantity":                   qty,
            # Show override values if set, otherwise original
            "part_volume_cm3":            float(cp.part_volume_cm3_override or part.part_volume_cm3 or 0),
            "aufmass_pct":                  float(cp.aufmass_pct_override or part.aufmass_pct or 0) or None,
            "support_volume_cm3":         float(cp.support_volume_cm3_override or part.support_volume_cm3 or 0),
            "part_height_mm":             float(cp.part_height_mm_override or part.part_height_mm or 0),
            "prep_time_min":              float(cp.prep_time_min_override or part.prep_time_min or 0) or None,
            "post_handling_time_min":     float(cp.post_handling_time_min_override or part.post_handling_time_min or 0) or None,
            "blasting_time_min":          float(cp.blasting_time_min_override or part.blasting_time_min or 0) or None,
            "leak_testing_time_min":      float(cp.leak_testing_time_min_override or part.leak_testing_time_min or 0) or None,
            "qc_time_min":                float(cp.qc_time_min_override or part.qc_time_min or 0) or None,
            "projected_xy_surface_mm2":   float(part.projected_xy_surface_mm2) if part.projected_xy_surface_mm2 else None,
            "manual_part_price_eur":      float(part.manual_part_price_eur) if part.manual_part_price_eur else None,
            "calc_part_price_eur":        float(cp.calc_part_price_eur) if cp.calc_part_price_eur else None,
            "calc_build_time_h":          float(cp.calc_build_time_h) if cp.calc_build_time_h else None,
            "price_reduction_eur":        savings_eur,
            "price_reduction_percent":    savings_pct,
        })

    # Combined build time = max over all parts (build job runs in parallel)
    max_build_time = max((p["calc_build_time_h"] or 0 for p in parts_data), default=0)
    # Original build time = sum of unique inquiry build times
    orig_build_times = {}
    for p in parts_data:
        if p["inquiry_id"] and p["manual_build_time_h"]:
            orig_build_times[p["inquiry_id"]] = p["manual_build_time_h"]
    orig_build_time_total = sum(orig_build_times.values())

    return {
        "calc_id":               calc.calc_id,
        "calc_number":           calc.calc_number,
        "calc_name":             calc.calc_name,
        "machine":               calc.machine,
        "material_group":        calc.material_group,
        "platform_surface_mm2":  float(calc.platform_surface_mm2),
        "platform_pct":          platform_pct,
        "start_date":            str(calc.start_date) if calc.start_date else None,
        "end_date":              str(calc.end_date) if calc.end_date else None,
        "status":                calc.status,
        "total_manual_price":    round(total_manual_price, 2),
        "total_calc_price":      round(total_calc_price, 2),
        "total_savings_eur":     round(total_manual_price - total_calc_price, 2) if total_calc_price else None,
        "total_savings_pct":     round((total_manual_price - total_calc_price) / total_manual_price * 100, 1) if total_calc_price and total_manual_price else None,
        "combined_build_time_h": round(max_build_time, 2),
        "original_build_time_h": round(orig_build_time_total, 2),
        "parts":                 parts_data,
        "created_at":            str(calc.created_at),
    }


@router.post("/")
def create_calculation(
    data: CalcCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if data.machine not in MACHINE_MATERIALS:
        raise HTTPException(status_code=400, detail=f"Ungültige Maschine: {data.machine}")
    calc = CombinedCalculation(
        calc_number=generate_calc_number(),
        calc_name=data.calc_name,
        machine=data.machine,
        material_group=data.material_group,
        platform_surface_mm2=MACHINE_PLATFORM_MM2[data.machine],
        start_date=data.start_date,
        end_date=data.end_date,
    )
    db.add(calc)
    db.commit()
    db.refresh(calc)
    return {"message": "Kalkulation erstellt", "calc_id": calc.calc_id, "calc_number": calc.calc_number}


@router.get("/")
def list_calculations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    calcs = db.query(CombinedCalculation).order_by(desc(CombinedCalculation.created_at)).all()
    return [serialize_calc(c, db) for c in calcs]


@router.get("/available-parts/{machine}/{material_group}")
def get_available_parts(
    machine: str,
    material_group: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all parts whose material is compatible with the calculation machine+material group.
    The original inquiry machine does NOT need to match — only the material matters.
    E.g. parts entered under M2_neu with 1.4404 are selectable for a M2_alt calculation."""

    # All inquiries — no machine filter
    inquiries = db.query(Inquiry).all()

    result = []
    for inq in inquiries:
        parts = db.query(Part).filter(Part.inquiry_id == inq.inquiry_id).all()
        inq_parts = []
        for p in parts:
            mg = get_material_group(p.material)
            if mg == material_group or p.material == material_group:
                inq_parts.append({
                    "part_id":                p.part_id,
                    "part_name":              p.part_name,
                    "material":               p.material,
                    "quantity":               p.quantity,
                    "part_volume_cm3":        float(p.part_volume_cm3) if p.part_volume_cm3 else None,
                    "support_volume_cm3":     float(p.support_volume_cm3) if p.support_volume_cm3 else None,
                    "part_height_mm":         float(p.part_height_mm) if p.part_height_mm else None,
                    "projected_xy_surface_mm2": float(p.projected_xy_surface_mm2) if p.projected_xy_surface_mm2 else None,
                    "manual_part_price_eur":  float(p.manual_part_price_eur) if p.manual_part_price_eur else None,
                })
        if inq_parts:
            result.append({
                "inquiry_id":      inq.inquiry_id,
                "inquiry_number":  inq.inquiry_number,
                "order_number":    inq.order_number,
                "customer_number": inq.customer_number,
                "status":          inq.status,
                "manual_build_time_h": float(inq.manual_build_time_h) if inq.manual_build_time_h else None,
                "parts":           inq_parts
            })
    return result


@router.get("/{calc_id}")
def get_calculation(
    calc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    calc = db.query(CombinedCalculation).filter(CombinedCalculation.calc_id == calc_id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Kalkulation nicht gefunden")
    return serialize_calc(calc, db)


@router.put("/{calc_id}")
def update_calculation(
    calc_id: int,
    data: CalcUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    calc = db.query(CombinedCalculation).filter(CombinedCalculation.calc_id == calc_id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Kalkulation nicht gefunden")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(calc, field, value)
    db.commit()
    return {"message": "Kalkulation aktualisiert"}


@router.delete("/{calc_id}")
def delete_calculation(
    calc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    calc = db.query(CombinedCalculation).filter(CombinedCalculation.calc_id == calc_id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Kalkulation nicht gefunden")
    db.delete(calc)
    db.commit()
    return {"message": "Kalkulation gelöscht. Bauteile bleiben in der Datenbank erhalten."}


@router.post("/{calc_id}/parts")
def add_parts(
    calc_id: int,
    data: AddPartsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    calc = db.query(CombinedCalculation).filter(CombinedCalculation.calc_id == calc_id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Kalkulation nicht gefunden")

    part_ids = data.part_ids
    if data.inquiry_id and not part_ids:
        parts = db.query(Part).filter(Part.inquiry_id == data.inquiry_id).all()
        part_ids = [p.part_id for p in parts]

    added = 0
    skipped_material = []
    for part_id in part_ids:
        part = db.query(Part).filter(Part.part_id == part_id).first()
        if not part:
            continue

        mat_group = get_material_group(part.material)
        if mat_group != calc.material_group and part.material != calc.material_group:
            skipped_material.append(part.part_name)
            continue

        existing = db.query(CalcPart).filter(
            CalcPart.calc_id == calc_id, CalcPart.part_id == part_id
        ).first()
        if existing:
            continue

        pred = predict(calc.machine, part.material, {
            "quantity":               part.quantity,
            "part_volume_cm3":        float(part.part_volume_cm3 or 0),
            "aufmass_pct":              float(part.aufmass_pct or 0),
            "support_volume_cm3":     float(part.support_volume_cm3 or 0),
            "part_height_mm":         float(part.part_height_mm or 0),
            "prep_time_min":          float(part.prep_time_min or 0),
            "post_handling_time_min": float(part.post_handling_time_min or 0),
            "blasting_time_min":      float(part.blasting_time_min or 0),
            "leak_testing_time_min":  float(part.leak_testing_time_min or 0),
            "qc_time_min":            float(part.qc_time_min or 0),
        })

        manual_price = float(part.manual_part_price_eur or 0)
        calc_price = pred.get("calc_part_price_eur")
        savings_eur = round(manual_price - calc_price, 2) if calc_price else None
        savings_pct = round((manual_price - calc_price) / manual_price * 100, 1) if calc_price and manual_price else None

        cp = CalcPart(
            calc_id=calc_id,
            part_id=part_id,
            calc_part_price_eur=calc_price,
            calc_build_time_h=pred.get("calc_build_time_h"),
            price_reduction_eur=savings_eur,
            price_reduction_percent=savings_pct,
        )
        db.add(cp)
        added += 1

    db.commit()
    msg = f"{added} Bauteile zur Kalkulation hinzugefügt."
    if skipped_material:
        msg += f" Übersprungen (falsches Material): {', '.join(skipped_material)}"
    return {"message": msg}


@router.delete("/{calc_id}/parts/{cp_id}")
def remove_part(
    calc_id: int,
    cp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cp = db.query(CalcPart).filter(CalcPart.id == cp_id, CalcPart.calc_id == calc_id).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Bauteil nicht in Kalkulation")
    db.delete(cp)
    db.commit()
    return {"message": "Bauteil aus Kalkulation entfernt"}


@router.put("/{calc_id}/parts/{cp_id}")
def update_calc_part(
    calc_id: int,
    cp_id: int,
    data: CalcPartUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cp = db.query(CalcPart).filter(CalcPart.id == cp_id, CalcPart.calc_id == calc_id).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Bauteil nicht in Kalkulation")

    calc = db.query(CombinedCalculation).filter(CombinedCalculation.calc_id == calc_id).first()
    part = db.query(Part).filter(Part.part_id == cp.part_id).first()

    # Store overrides on the CalcPart
    OVERRIDE_MAP = {
        "material_override":    "material_override",
        "quantity_override":    "quantity_override",
        "part_volume_cm3":      "part_volume_cm3_override",
        "aufmass_pct":          "aufmass_pct_override",
        "support_volume_cm3":   "support_volume_cm3_override",
        "part_height_mm":       "part_height_mm_override",
        "prep_time_min":        "prep_time_min_override",
        "post_handling_time_min": "post_handling_time_min_override",
        "blasting_time_min":    "blasting_time_min_override",
        "leak_testing_time_min":"leak_testing_time_min_override",
        "qc_time_min":          "qc_time_min_override",
    }
    for field, value in data.dict(exclude_unset=True).items():
        override_field = OVERRIDE_MAP.get(field, field)
        if hasattr(cp, override_field):
            setattr(cp, override_field, value)

    # Re-run regression with merged data
    material = cp.material_override or part.material
    pred_data = get_part_data_for_predict(part, cp)
    pred = predict(calc.machine, material, pred_data)

    cp.calc_part_price_eur = pred.get("calc_part_price_eur")
    cp.calc_build_time_h = pred.get("calc_build_time_h")

    qty = pred_data["quantity"]
    manual_price = float(part.manual_part_price_eur or 0) * qty
    calc_price_total = float(cp.calc_part_price_eur or 0) * qty if cp.calc_part_price_eur else None
    cp.price_reduction_eur = round(manual_price - calc_price_total, 2) if calc_price_total else None
    cp.price_reduction_percent = round((manual_price - calc_price_total) / manual_price * 100, 1) if calc_price_total and manual_price else None

    db.commit()
    return {"message": "Bauteil aktualisiert und neu berechnet"}
