from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from pydantic import BaseModel
from decimal import Decimal
from datetime import date
import pandas as pd
import io

from database import get_db
from models import Inquiry, Part, Customer, User, MACHINE_MATERIALS, MACHINE_PLATFORM_MM2
from routers.auth import get_current_user

router = APIRouter(prefix="/api/datenbank", tags=["datenbank"])


class PartIn(BaseModel):
    material: str
    part_name: str
    quantity: int = 1
    part_volume_mm3: float
    stock_cm3: Optional[float] = None
    support_volume_cm3: float
    part_height_mm: float
    prep_time_min: Optional[float] = None
    post_handling_time_min: Optional[float] = None
    blasting_time_min: Optional[float] = None
    leak_testing_time_min: Optional[float] = None
    qc_time_min: Optional[float] = None
    projected_xy_surface_mm2: Optional[float] = None
    manual_part_price_eur: Optional[float] = None
    manual_build_time_h: Optional[float] = None


class InquiryCreate(BaseModel):
    inquiry_number: str
    order_number: Optional[str] = None
    customer_number: str
    inquiry_date: Optional[date] = None
    order_date: Optional[date] = None
    requested_delivery_date: Optional[date] = None
    status: str = "Anfrage"
    machine: str
    parts: List[PartIn]


class InquiryUpdate(BaseModel):
    order_number: Optional[str] = None
    order_date: Optional[date] = None
    requested_delivery_date: Optional[date] = None
    status: Optional[str] = None
    machine: Optional[str] = None


class PartUpdate(BaseModel):
    material: Optional[str] = None
    part_name: Optional[str] = None
    quantity: Optional[int] = None
    part_volume_mm3: Optional[float] = None
    stock_cm3: Optional[float] = None
    support_volume_cm3: Optional[float] = None
    part_height_mm: Optional[float] = None
    prep_time_min: Optional[float] = None
    post_handling_time_min: Optional[float] = None
    blasting_time_min: Optional[float] = None
    leak_testing_time_min: Optional[float] = None
    qc_time_min: Optional[float] = None
    projected_xy_surface_mm2: Optional[float] = None
    manual_part_price_eur: Optional[float] = None
    manual_build_time_h: Optional[float] = None


def ensure_customer(customer_number: str, db: Session):
    customer = db.query(Customer).filter(Customer.customer_number == customer_number).first()
    if not customer:
        customer = Customer(customer_number=customer_number)
        db.add(customer)
        db.commit()
    return customer


def calculate_platform_percent(parts: list, machine: str) -> float:
    """Calculate total platform occupation percentage for a set of parts."""
    platform = MACHINE_PLATFORM_MM2.get(machine, 0)
    if platform == 0:
        return 0
    total_surface = sum(
        float(p.projected_xy_surface_mm2 or 0) * p.quantity
        for p in parts
        if p.projected_xy_surface_mm2
    )
    return round(total_surface / platform * 100, 1)


def serialize_inquiry(inq: Inquiry, db: Session) -> dict:
    parts = db.query(Part).filter(Part.inquiry_id == inq.inquiry_id).all()
    platform_pct = calculate_platform_percent(parts, inq.machine)
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
        "platform_occupation_pct":  platform_pct,
        "parts":                    [serialize_part(p) for p in parts],
    }


def serialize_part(p: Part) -> dict:
    return {
        "part_id":                  p.part_id,
        "inquiry_id":               p.inquiry_id,
        "material":                 p.material,
        "part_name":                p.part_name,
        "quantity":                 p.quantity,
        "part_volume_mm3":          float(p.part_volume_mm3) if p.part_volume_mm3 else None,
        "stock_cm3":                float(p.stock_cm3) if p.stock_cm3 else None,
        "support_volume_cm3":       float(p.support_volume_cm3) if p.support_volume_cm3 else None,
        "part_height_mm":           float(p.part_height_mm) if p.part_height_mm else None,
        "prep_time_min":            float(p.prep_time_min) if p.prep_time_min else None,
        "post_handling_time_min":   float(p.post_handling_time_min) if p.post_handling_time_min else None,
        "blasting_time_min":        float(p.blasting_time_min) if p.blasting_time_min else None,
        "leak_testing_time_min":    float(p.leak_testing_time_min) if p.leak_testing_time_min else None,
        "qc_time_min":              float(p.qc_time_min) if p.qc_time_min else None,
        "projected_xy_surface_mm2": float(p.projected_xy_surface_mm2) if p.projected_xy_surface_mm2 else None,
        "manual_part_price_eur":    float(p.manual_part_price_eur) if p.manual_part_price_eur else None,
        "manual_build_time_h":      float(p.manual_build_time_h) if p.manual_build_time_h else None,
    }


@router.post("/")
def create_inquiry(
    data: InquiryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Validate machine
    if data.machine not in MACHINE_MATERIALS:
        raise HTTPException(status_code=400, detail=f"Ungültige Maschine: {data.machine}")

    # Validate materials
    allowed = MACHINE_MATERIALS[data.machine]
    for part in data.parts:
        if part.material not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Material '{part.material}' nicht verfügbar für {data.machine}. Erlaubt: {', '.join(allowed)}"
            )

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
    )
    db.add(inq)
    db.flush()

    for p in data.parts:
        part = Part(inquiry_id=inq.inquiry_id, **p.dict())
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

    inquiries = query.all()
    return [serialize_inquiry(inq, db) for inq in inquiries]


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
    return {"message": "Bauteil aktualisiert"}


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


@router.post("/import")
async def import_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Import inquiries/parts from Excel (.xlsx) or tab-delimited TXT file."""
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

    # Normalize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    required = ["anfragenummer", "kundennummer", "maschine", "material", "bauteilname"]
    missing = [r for r in required if r not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Fehlende Pflicht-Spalten: {', '.join(missing)}. Erforderlich: {', '.join(required)}"
        )

    imported = 0
    errors = []

    # Group by inquiry number
    for inquiry_number, group in df.groupby("anfragenummer"):
        first = group.iloc[0]
        machine = str(first.get("maschine", "")).strip()
        customer_number = str(first.get("kundennummer", "")).strip()

        if machine not in MACHINE_MATERIALS:
            errors.append(f"Zeile {group.index[0]+2}: Ungültige Maschine '{machine}'")
            continue

        ensure_customer(customer_number, db)

        inq = Inquiry(
            inquiry_number=str(inquiry_number).strip(),
            order_number=str(first.get("auftragsnummer", "") or "").strip() or None,
            customer_number=customer_number,
            status="Auftrag" if pd.notna(first.get("auftragsnummer")) and str(first.get("auftragsnummer", "")).strip() else "Anfrage",
            machine=machine,
        )
        db.add(inq)
        db.flush()

        for _, row in group.iterrows():
            material = str(row.get("material", "")).strip()
            if material not in MACHINE_MATERIALS.get(machine, []):
                errors.append(f"Anfrage {inquiry_number}: Material '{material}' nicht für {machine} verfügbar")
                continue

            part = Part(
                inquiry_id=inq.inquiry_id,
                material=material,
                part_name=str(row.get("bauteilname", "")).strip(),
                quantity=int(row.get("anzahl", 1) or 1),
                part_volume_mm3=float(row.get("bauteilvolumen_mm3", 0) or 0),
                stock_cm3=float(row.get("materialeinsatz_cm3", 0) or 0) or None,
                support_volume_cm3=float(row.get("stuetzstruktur_cm3", 0) or 0),
                part_height_mm=float(row.get("bauhoehe_mm", 0) or 0),
                prep_time_min=float(row.get("vorbereitung_min", 0) or 0) or None,
                post_handling_time_min=float(row.get("nachbearbeitung_min", 0) or 0) or None,
                blasting_time_min=float(row.get("strahlen_min", 0) or 0) or None,
                leak_testing_time_min=float(row.get("dichtheitspruefung_min", 0) or 0) or None,
                qc_time_min=float(row.get("qualitaetskontrolle_min", 0) or 0) or None,
                projected_xy_surface_mm2=float(row.get("xy_flaeche_mm2", 0) or 0) or None,
                manual_part_price_eur=float(row.get("stueckpreis_eur", 0) or 0) or None,
                manual_build_time_h=float(row.get("bauzeit_h", 0) or 0) or None,
            )
            db.add(part)

        imported += 1

    db.commit()
    return {
        "message": f"{imported} Anfragen erfolgreich importiert.",
        "errors": errors
    }
