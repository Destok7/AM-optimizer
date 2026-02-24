from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from database import get_db
from models import EmailNotification, CombinedCalculation, Customer, User
from routers.auth import get_current_user
from services.gpt_service import generate_email

router = APIRouter(prefix="/api/emails", tags=["emails"])


class EmailGenerateRequest(BaseModel):
    calc_id: int
    inquiry_number: str
    order_number: Optional[str] = None


class EmailUpdate(BaseModel):
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    status: Optional[str] = None


def serialize_email(n: EmailNotification) -> dict:
    return {
        "notification_id":  n.notification_id,
        "calc_id":          n.calc_id,
        "customer_number":  n.customer_number,
        "inquiry_number":   n.inquiry_number,
        "order_number":     n.order_number,
        "notification_type":n.notification_type,
        "email_subject":    n.email_subject,
        "email_body":       n.email_body,
        "status":           n.status,
        "generated_at":     str(n.generated_at),
    }


@router.post("/generate")
def generate_notification(
    data: EmailGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a GPT-4 email draft for a combined calculation."""
    calc = db.query(CombinedCalculation).filter(CombinedCalculation.calc_id == data.calc_id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Kalkulation nicht gefunden")

    # Get serialized calc data with all parts and savings
    from routers.kalkulation import serialize_calc
    calc_data = serialize_calc(calc, db)

    # Filter parts for this specific inquiry
    inquiry_parts = [p for p in calc_data["parts"] if p.get("inquiry_number") == data.inquiry_number]
    if not inquiry_parts:
        raise HTTPException(status_code=404, detail="Keine Bauteile für diese Anfragenummer in der Kalkulation")

    # Get customer number
    customer_number = inquiry_parts[0].get("customer_number", "")

    # Generate with GPT
    result = generate_email(calc_data, data.inquiry_number, data.order_number)

    # Save draft
    notification = EmailNotification(
        calc_id=data.calc_id,
        customer_number=customer_number,
        inquiry_number=data.inquiry_number,
        order_number=data.order_number,
        notification_type="kombinierte_kalkulation",
        email_subject=result["subject"],
        email_body=result["body"],
        status="draft",
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    return serialize_email(notification)


@router.get("/")
def list_emails(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(EmailNotification).order_by(EmailNotification.generated_at.desc())
    if status:
        query = query.filter(EmailNotification.status == status)
    return [serialize_email(n) for n in query.all()]


@router.get("/{notification_id}")
def get_email(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    n = db.query(EmailNotification).filter(EmailNotification.notification_id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="E-Mail nicht gefunden")
    return serialize_email(n)


@router.put("/{notification_id}")
def update_email(
    notification_id: int,
    data: EmailUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    n = db.query(EmailNotification).filter(EmailNotification.notification_id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="E-Mail nicht gefunden")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(n, field, value)
    db.commit()
    return {"message": "E-Mail aktualisiert"}


@router.delete("/{notification_id}")
def delete_email(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    n = db.query(EmailNotification).filter(EmailNotification.notification_id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="E-Mail nicht gefunden")
    db.delete(n)
    db.commit()
    return {"message": "E-Mail gelöscht"}
