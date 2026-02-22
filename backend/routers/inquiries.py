from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from pydantic import BaseModel
from decimal import Decimal
from datetime import date
from database import get_db
from models import Inquiry, Customer, User
from routers.auth import get_current_user

router = APIRouter(prefix="/api/inquiries", tags=["inquiries"])


class InquiryCreate(BaseModel):
    customer_number: str
    inquiry_number: str
    order_number: Optional[str] = None
    inquiry_name: str
    inquiry_date: Optional[date] = None

    part_name: str
    quantity: int
    part_volume_cm3: Decimal
    stock_percent: Optional[Decimal] = None
    support_volume_percent: Decimal
    part_height_mm: Decimal

    prep_time_h: Optional[Decimal] = None
    post_handling_time_h: Optional[Decimal] = None
    blasting_time_h: Optional[Decimal] = None
    leak_testing_time_h: Optional[Decimal] = None
    qc_time_h: Optional[Decimal] = None

    projected_xy_surface_cm2: Optional[Decimal] = None
    requested_delivery_date: Optional[date] = None
    lead_time_flexible: bool = False


class InquiryUpdate(BaseModel):
    status: Optional[str] = None
    order_number: Optional[str] = None
    projected_xy_surface_cm2: Optional[Decimal] = None
    requested_delivery_date: Optional[date] = None
    lead_time_flexible: Optional[bool] = None
    estimated_part_price_eur: Optional[Decimal] = None
    estimated_build_time_h: Optional[Decimal] = None


def ensure_customer_exists(customer_number: str, db: Session):
    customer = db.query(Customer).filter(Customer.customer_number == customer_number).first()
    if not customer:
        customer = Customer(customer_number=customer_number)
        db.add(customer)
        db.commit()
    return customer


@router.post("/")
def create_inquiry(
    data: InquiryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_customer_exists(data.customer_number, db)

    inquiry = Inquiry(**data.dict())
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)
    return {"message": "Anfrage erfolgreich erstellt", "inquiry_id": inquiry.inquiry_id}


@router.get("/")
def list_inquiries(
    status: Optional[str] = None,
    customer_number: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Inquiry)
    if status:
        query = query.filter(Inquiry.status == status)
    if customer_number:
        query = query.filter(Inquiry.customer_number == customer_number)
    inquiries = query.order_by(desc(Inquiry.created_at)).all()

    result = []
    for inq in inquiries:
        result.append({
            "inquiry_id": inq.inquiry_id,
            "customer_number": inq.customer_number,
            "inquiry_number": inq.inquiry_number,
            "order_number": inq.order_number,
            "inquiry_name": inq.inquiry_name,
            "inquiry_date": str(inq.inquiry_date) if inq.inquiry_date else None,
            "status": inq.status,
            "part_name": inq.part_name,
            "quantity": inq.quantity,
            "part_volume_cm3": float(inq.part_volume_cm3) if inq.part_volume_cm3 else None,
            "stock_percent": float(inq.stock_percent) if inq.stock_percent else None,
            "support_volume_percent": float(inq.support_volume_percent) if inq.support_volume_percent else None,
            "part_height_mm": float(inq.part_height_mm) if inq.part_height_mm else None,
            "projected_xy_surface_cm2": float(inq.projected_xy_surface_cm2) if inq.projected_xy_surface_cm2 else None,
            "requested_delivery_date": str(inq.requested_delivery_date) if inq.requested_delivery_date else None,
            "lead_time_flexible": inq.lead_time_flexible,
            "estimated_part_price_eur": float(inq.estimated_part_price_eur) if inq.estimated_part_price_eur else None,
            "estimated_build_time_h": float(inq.estimated_build_time_h) if inq.estimated_build_time_h else None,
            "created_at": str(inq.created_at)
        })
    return result


@router.get("/{inquiry_id}")
def get_inquiry(
    inquiry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inq = db.query(Inquiry).filter(Inquiry.inquiry_id == inquiry_id).first()
    if not inq:
        raise HTTPException(status_code=404, detail="Anfrage nicht gefunden")
    return inq


@router.put("/{inquiry_id}")
def update_inquiry(
    inquiry_id: int,
    data: InquiryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inq = db.query(Inquiry).filter(Inquiry.inquiry_id == inquiry_id).first()
    if not inq:
        raise HTTPException(status_code=404, detail="Anfrage nicht gefunden")

    for field, value in data.dict(exclude_unset=True).items():
        setattr(inq, field, value)

    db.commit()
    return {"message": "Anfrage aktualisiert"}


@router.delete("/{inquiry_id}")
def delete_inquiry(
    inquiry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inq = db.query(Inquiry).filter(Inquiry.inquiry_id == inquiry_id).first()
    if not inq:
        raise HTTPException(status_code=404, detail="Anfrage nicht gefunden")
    db.delete(inq)
    db.commit()
    return {"message": "Anfrage gelöscht"}
