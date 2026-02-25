from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import date
import pandas as pd
import numpy as np
import io
import re

from database import get_db
from models import Inquiry, Part, Customer, User, MACHINE_MATERIALS, MACHINE_PLATFORM_MM2
from routers.auth import get_current_user

router = APIRouter(prefix="/api/datenbank", tags=["datenbank"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PartIn(BaseModel):
    material: str
    part_name: str
    quantity: int = 1
    part_volume_cm3: float           # stored as cm³
    aufmass_pct: Optional[float] = None   # Aufmaß [%] — replaces Materialeinsatz
    support_volume_cm3: float
    part_height_mm: float
    prep_time_min: Optional[float] = None
    post_handling_time_min: Optional[float] = None
    blasting_time_min: Optional[float] = None
    leak_testing_time_min: Optional[float] = None
    qc_time_min: Optional[float] = None
    projected_xy_surface_mm2: Optional[float] = None
    manual_part_price_eur: Optional[float] = None


class InquiryCreate(BaseModel):
    inquiry_number: str
    order_number: Optional[str] = None
    customer_number: str
    inquiry_date: Optional[date] = None
    order_date: Optional[date] = None
    requested_delivery_date: Optional[date] = None
    status: str = "Anfrage"
    machine: str
    manual_build_time_h: Optional[float] = None
    parts: List[PartIn]


class InquiryUpdate(BaseModel):
    order_number: Optional[str] = None
    order_date: Optional[date] = None
    requested_delivery_date: Optional[date] = None
    status: Optional[str] = None
    machine: Optional[str] = None
    manual_build_time_h: Optional[float] = None


class PartUpdate(BaseModel):
    material: Optional[str] = None
    part_name: Optional[str] = None
    quantity: Optional[int] = None
    part_volume_cm3: Optional[float] = None
    aufmass_pct: Optional[float] = None
    support_volume_cm3: Optional[float] = None
    part_height_mm: Optional[float] = None
    prep_time_min: Optional[float] = None
    post_handling_time_min: Optional[float] = None
    blasting_time_min: Optional[float] = None
    leak_testing_time_min: Optional[float] = None
    qc_time_min: Optional[float] = None
    projected_xy_surface_mm2: Optional[float] = None
    manual_part_price_eur: Optional[float] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Material name normalisations (handles typos / missing dots)
MATERIAL_ALIASES = {
    "14404":    "1.4404",
    "1.4404":   "1.4404",
    "14301":    "1.4301",
    "alsi10mg": "AlSi10Mg",
    "alsi":     "AlSi10Mg",
    "in718":    "IN718",
    "in625":    "IN625",
    "inconel718": "IN718",
    "inconel625": "IN625",
}

def normalize_material(raw: str) -> str:
    key = str(raw).strip().lower().replace(" ", "")
    return MATERIAL_ALIASES.get(key, str(raw).strip())


def ensure_customer(customer_number: str, db: Session):
    customer = db.query(Customer).filter(Customer.customer_number == customer_number).first()
    if not customer:
        customer = Customer(customer_number=customer_number)
        db.add(customer)
        db.commit()
    return customer


def calculate_platform_percent(parts: list, machine: str) -> float:
    platform = MACHINE_PLATFORM_MM2.get(machine, 0)
    if platform == 0:
        return 0
    total = sum(
        float(p.projected_xy_surface_mm2 or 0) * p.quantity
        for p in parts if p.projected_xy_surface_mm2
    )
    return round(total / platform * 100, 1)


def safe_float(val, default=None):
    try:
        v = float(val)
        if np.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def serialize_part(p: Part) -> dict:
    return {
        "part_id":                  p.part_id,
        "inquiry_id":               p.inquiry_id,
        "material":                 p.material,
        "part_name":                p.part_name,
        "quantity":                 p.quantity,
        "part_volume_cm3":          float(p.part_volume_cm3) if p.part_volume_cm3 else None,
        "aufmass_pct":              float(p.aufmass_pct) if p.aufmass_pct else None,
        "support_volume_cm3":       float(p.support_volume_cm3) if p.support_volume_cm3 else None,
        "part_height_mm":           float(p.part_height_mm) if p.part_height_mm else None,
        "prep_time_min":            float(p.prep_time_min) if p.prep_time_min else None,
        "post_handling_time_min":   float(p.post_handling_time_min) if p.post_handling_time_min else None,
        "blasting_time_min":        float(p.blasting_time_min) if p.blasting_time_min else None,
        "leak_testing_time_min":    float(p.leak_testing_time_min) if p.leak_testing_time_min else None,
        "qc_time_min":              float(p.qc_time_min) if p.qc_time_min else None,
        "projected_xy_surface_mm2": float(p.projected_xy_surface_mm2) if p.projected_xy_surface_mm2 else None,
        "manual_part_price_eur":    float(p.manual_part_price_eur) if p.manual_part_price_eur else None,
    }


def serialize_inquiry(inq: Inquiry, db: Session) -> dict:
    parts = db.query(Part).filter(Part.inquiry_id == inq.inquiry_id).all()
    return {
        "inquiry_id":               inq.inquiry_id,
        "inquiry_number":           inq.inquiry_number,
        "order_number":             inq.order_number,
        "customer_number":          inq.customer_number,
        "inquiry_date":             str(inq.inquiry_date) if inq.inquiry_date else None,
        "order_date":               str(inq.order_date) if inq.order_date else None,
        "requested_delivery_date":  str(inq.requested_delivery_date) if inq.requested_delivery_date else None,
        "status":                   inq.status,
        "machine":                  inq.machine,
        "manual_build_time_h":      float(inq.manual_build_time_h) if inq.manual_build_time_h else None,
        "platform_occupation_pct":  calculate_platform_percent(parts, inq.machine),
        "parts":                    [serialize_part(p) for p in parts],
    }


# ---------------------------------------------------------------------------
# Column name fuzzy-mapping for Excel import
# ---------------------------------------------------------------------------

# Maps canonical internal names → list of accepted column name variants
COLUMN_MAP = {
    "anfragenummer":        ["anfragenummer"],
    "auftragsnummer":       ["auftragsnummer", "auftragsnummer (optional)", "auftragsnr"],
    "kundennummer":         ["kundennummer", "kundennr", "customer"],
    "maschine":             ["maschine", "machine"],
    "material":             ["material"],
    "bauteilname":          ["bauteilname", "bauteil", "partname", "name", "bezeichnung"],
    "anzahl":               ["anzahl", "quantity", "menge", "stueckzahl"],
    # volume in Excel may be mm³ or cm³ — we detect and convert
    "bauteilvolumen":       ["bautielvolumen_mm", "bauteilvolumen_mm", "bauteilvolumen_cm",
                             "bautielvolumen_cm", "bauteilvolumen", "bautielvolumen",
                             "volumen", "volume_mm3", "volume_cm3"],
    "volumen_unit":         [],   # derived: "mm3" or "cm3"
    "stuetzstruktur_cm3":   ["stuetzstruktur_cm3", "stuetzstruktur", "support_cm3",
                             "supportvolumen", "support_volume_cm3"],
    "bauhoehe_mm":          ["bauhoehe_mm", "bauhoehe", "hoehe_mm", "height_mm", "hoehe"],
    "aufmass_pct":          ["aufmass_pct", "aufmass", "aufmass_%", "materialeinsatz_pct",
                             "materialeinsatz_%", "overmeasure", "allowance"],
    "vorbereitung_min":     ["vorbereitung_min", "vorbereitung", "prep_time_min", "prep_min"],
    "nachbearbeitung_min":  ["nachbearbeitung_min", "nachbearbeitung", "post_min",
                             "post_handling_time_min"],
    "strahlen_min":         ["strahlen_min", "strahlen", "blasting_min", "blast_min"],
    "dichtheitspruefung_min":["dichtheitspruefung_min", "dichtheitspruefung",
                              "leak_testing_min", "leak_min"],
    "qualitaetskontrolle_min":["qualitaetskontrolle_min", "qualitaetskontrolle",
                               "qc_min", "qk_min"],
    "xy_flaeche_mm2":       ["xy_flaeche_mm2", "xy_flaeche", "projected_xy", "xy_surface"],
    "stueckpreis_eur":      ["stueckpreis_eur", "stueckpreis", "preis_eur", "price_eur",
                             "einheitspreis"],
    "bauzeit_h":            ["bauzeit_h", "bauzeit", "build_time_h", "buildtime"],
}


def map_columns(df: pd.DataFrame) -> dict:
    """Returns {canonical_name: actual_df_column} for all matched columns."""
    # Normalise df column names for matching
    norm = {c: re.sub(r'[^a-z0-9]', '_', c.lower().strip()).rstrip('_') for c in df.columns}
    # Reverse: normalised → original
    rev = {v: k for k, v in norm.items()}

    mapping = {}
    for canonical, variants in COLUMN_MAP.items():
        if canonical == "volumen_unit":
            continue
        for variant in variants:
            v_norm = re.sub(r'[^a-z0-9]', '_', variant.lower()).rstrip('_')
            if v_norm in rev:
                mapping[canonical] = rev[v_norm]
                break

    # Detect volume unit from actual column name
    if "bauteilvolumen" in mapping:
        col = mapping["bauteilvolumen"].lower()
        if "cm" in col:
            mapping["volumen_unit"] = "cm3"
        else:
            mapping["volumen_unit"] = "mm3"   # default: mm³ → convert to cm³
    return mapping


def get_val(row, col_map, canonical, default=None):
    col = col_map.get(canonical)
    if col is None:
        return default
    return safe_float(row.get(col), default)


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.post("/")
def create_inquiry(
    data: InquiryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if data.machine not in MACHINE_MATERIALS:
        raise HTTPException(status_code=400, detail=f"Ungültige Maschine: {data.machine}")
    allowed = MACHINE_MATERIALS[data.machine]
    for part in data.parts:
        mat = normalize_material(part.material)
        if mat not in allowed:
            raise HTTPException(status_code=400,
                detail=f"Material '{mat}' nicht verfügbar für {data.machine}. Erlaubt: {', '.join(allowed)}")
        part.material = mat

    ensure_customer(data.customer_number, db)
    inq = Inquiry(
        inquiry_number=data.inquiry_number,
        order_number=data.order_number,
        customer_number=data.customer_number,
        inquiry_date=data.inquiry_date,
        order_date=data.order_date,
        requested_delivery_date=data.requested_delivery_date,
        status=data.status,
        machine=data.machine,
        manual_build_time_h=data.manual_build_time_h,
    )
    db.add(inq)
    db.flush()

    for p in data.parts:
        part = Part(
            inquiry_id=inq.inquiry_id,
            material=p.material,
            part_name=p.part_name,
            quantity=p.quantity,
            part_volume_cm3=p.part_volume_cm3,
            aufmass_pct=p.aufmass_pct,
            support_volume_cm3=p.support_volume_cm3,
            part_height_mm=p.part_height_mm,
            prep_time_min=p.prep_time_min,
            post_handling_time_min=p.post_handling_time_min,
            blasting_time_min=p.blasting_time_min,
            leak_testing_time_min=p.leak_testing_time_min,
            qc_time_min=p.qc_time_min,
            projected_xy_surface_mm2=p.projected_xy_surface_mm2,
            manual_part_price_eur=p.manual_part_price_eur,
        )
        db.add(part)

    db.commit()
    db.refresh(inq)
    return {"message": "Erfolgreich gespeichert", "inquiry_id": inq.inquiry_id}


@router.get("/")
def list_inquiries(
    status: Optional[str] = None,
    machine: Optional[str] = None,
    customer_number: Optional[str] = None,
    sort_by: str = "inquiry_number",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Inquiry)
    if status:
        query = query.filter(Inquiry.status == status)
    if machine:
        query = query.filter(Inquiry.machine == machine)
    if customer_number:
        query = query.filter(Inquiry.customer_number == customer_number)
    if sort_by == "order_number":
        query = query.order_by(Inquiry.order_number.asc().nullslast(), Inquiry.inquiry_number.asc())
    else:
        query = query.order_by(Inquiry.inquiry_number.asc())
    return [serialize_inquiry(inq, db) for inq in query.all()]


@router.get("/{inquiry_id}")
def get_inquiry(
    inquiry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inq = db.query(Inquiry).filter(Inquiry.inquiry_id == inquiry_id).first()
    if not inq:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return serialize_inquiry(inq, db)


@router.put("/{inquiry_id}")
def update_inquiry(
    inquiry_id: int,
    data: InquiryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inq = db.query(Inquiry).filter(Inquiry.inquiry_id == inquiry_id).first()
    if not inq:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(inq, field, value)
    db.commit()
    return {"message": "Aktualisiert"}


@router.delete("/{inquiry_id}")
def delete_inquiry(
    inquiry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inq = db.query(Inquiry).filter(Inquiry.inquiry_id == inquiry_id).first()
    if not inq:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    db.delete(inq)
    db.commit()
    return {"message": "Gelöscht"}


@router.put("/parts/{part_id}")
def update_part(
    part_id: int,
    data: PartUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    part = db.query(Part).filter(Part.part_id == part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="Bauteil nicht gefunden")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(part, field, value)
    db.commit()
    return {"message": "Bauteil aktualisiert", "part": serialize_part(part)}


@router.delete("/parts/{part_id}")
def delete_part(
    part_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    part = db.query(Part).filter(Part.part_id == part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="Bauteil nicht gefunden")
    db.delete(part)
    db.commit()
    return {"message": "Bauteil gelöscht"}


# ---------------------------------------------------------------------------
# Import endpoint
# ---------------------------------------------------------------------------

@router.post("/{inquiry_id}/parts")
def add_part_to_inquiry(
    inquiry_id: int,
    data: PartIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inq = db.query(Inquiry).filter(Inquiry.inquiry_id == inquiry_id).first()
    if not inq:
        raise HTTPException(status_code=404, detail="Anfrage nicht gefunden")

    mat = normalize_material(data.material)
    allowed = MACHINE_MATERIALS.get(inq.machine, [])
    if mat not in allowed:
        raise HTTPException(status_code=400,
            detail=f"Material '{mat}' nicht verfügbar für {inq.machine}. Erlaubt: {', '.join(allowed)}")

    part = Part(
        inquiry_id=inquiry_id,
        material=mat,
        part_name=data.part_name,
        quantity=data.quantity,
        part_volume_cm3=data.part_volume_cm3,
        aufmass_pct=data.aufmass_pct,
        support_volume_cm3=data.support_volume_cm3,
        part_height_mm=data.part_height_mm,
        prep_time_min=data.prep_time_min,
        post_handling_time_min=data.post_handling_time_min,
        blasting_time_min=data.blasting_time_min,
        leak_testing_time_min=data.leak_testing_time_min,
        qc_time_min=data.qc_time_min,
        projected_xy_surface_mm2=data.projected_xy_surface_mm2,
        manual_part_price_eur=data.manual_part_price_eur,
    )
    db.add(part)
    db.commit()
    db.refresh(part)
    return {"message": "Bauteil hinzugefügt", "part_id": part.part_id}



@router.post("/import")
async def import_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    content = await file.read()
    filename = file.filename.lower()
    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        elif filename.endswith(".txt") or filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), sep=None, engine="python")
        else:
            raise HTTPException(status_code=400, detail="Nur .xlsx, .xls oder .txt/.csv Dateien erlaubt.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fehler beim Lesen der Datei: {str(e)}")

    col_map = map_columns(df)

    # Check required columns
    required = ["anfragenummer", "kundennummer", "maschine", "material", "bauteilname"]
    missing = [r for r in required if r not in col_map]
    if missing:
        available = list(df.columns)
        raise HTTPException(status_code=400,
            detail=f"Fehlende Pflicht-Spalten: {', '.join(missing)}. "
                   f"Gefundene Spalten in Datei: {', '.join(available)}")

    # Convert df to row dicts using original column names
    rows = df.to_dict(orient="records")

    imported = 0
    errors = []
    volume_unit = col_map.get("volumen_unit", "mm3")

    # Group by inquiry number
    inq_groups: dict = {}
    for row in rows:
        inq_num = str(row.get(col_map["anfragenummer"], "")).strip()
        if not inq_num:
            continue
        inq_groups.setdefault(inq_num, []).append(row)

    for inquiry_number, group in inq_groups.items():
        first = group[0]

        machine = str(first.get(col_map.get("maschine", ""), "") or "").strip()
        customer_number = str(first.get(col_map.get("kundennummer", ""), "") or "").strip()

        if machine not in MACHINE_MATERIALS:
            errors.append(f"Anfrage {inquiry_number}: Ungültige Maschine '{machine}'")
            continue

        order_number = None
        if "auftragsnummer" in col_map:
            raw_order = first.get(col_map["auftragsnummer"])
            if raw_order and str(raw_order).strip() and str(raw_order).strip().lower() not in ("nan", "none", ""):
                order_number = str(raw_order).strip()

        # Bauzeit is per inquiry (same value repeated on each row — take first)
        bauzeit = get_val(first, col_map, "bauzeit_h")

        ensure_customer(customer_number, db)

        inq = Inquiry(
            inquiry_number=inquiry_number,
            order_number=order_number,
            customer_number=customer_number,
            status="Auftrag" if order_number else "Anfrage",
            machine=machine,
            manual_build_time_h=bauzeit,
        )
        db.add(inq)
        db.flush()

        for row in group:
            raw_material = str(row.get(col_map["material"], "") or "").strip()
            material = normalize_material(raw_material)

            if material not in MACHINE_MATERIALS.get(machine, []):
                errors.append(
                    f"Anfrage {inquiry_number}, Bauteil '{row.get(col_map['bauteilname'], '?')}': "
                    f"Material '{material}' nicht für {machine} verfügbar "
                    f"(erlaubt: {', '.join(MACHINE_MATERIALS[machine])})"
                )
                continue

            # Volume conversion: if mm³ in file, convert to cm³
            raw_vol = get_val(row, col_map, "bauteilvolumen", 0)
            if volume_unit == "mm3":
                vol_cm3 = round(raw_vol / 1000, 4)
            else:
                vol_cm3 = raw_vol

            part = Part(
                inquiry_id=inq.inquiry_id,
                material=material,
                part_name=str(row.get(col_map["bauteilname"], "") or "").strip(),
                quantity=int(safe_float(row.get(col_map.get("anzahl", ""), 1), 1) or 1),
                part_volume_cm3=vol_cm3,
                aufmass_pct=get_val(row, col_map, "aufmass_pct"),
                support_volume_cm3=get_val(row, col_map, "stuetzstruktur_cm3", 0),
                part_height_mm=get_val(row, col_map, "bauhoehe_mm", 0),
                prep_time_min=get_val(row, col_map, "vorbereitung_min"),
                post_handling_time_min=get_val(row, col_map, "nachbearbeitung_min"),
                blasting_time_min=get_val(row, col_map, "strahlen_min"),
                leak_testing_time_min=get_val(row, col_map, "dichtheitspruefung_min"),
                qc_time_min=get_val(row, col_map, "qualitaetskontrolle_min"),
                projected_xy_surface_mm2=get_val(row, col_map, "xy_flaeche_mm2"),
                manual_part_price_eur=get_val(row, col_map, "stueckpreis_eur"),
            )
            db.add(part)

        imported += 1

    db.commit()
    return {
        "message": f"{imported} Anfrage(n) erfolgreich importiert.",
        "column_mapping": {k: v for k, v in col_map.items() if k != "volumen_unit"},
        "volume_unit_detected": volume_unit,
        "errors": errors
    }
