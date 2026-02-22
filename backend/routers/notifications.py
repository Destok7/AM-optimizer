from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import EmailNotification, Inquiry, BuildJob, BuildJobInquiry, User
from routers.auth import get_current_user
from services.gpt_service import generate_email_draft

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class GenerateEmailRequest(BaseModel):
    inquiry_id: int
    job_id: int
    notification_type: str  # 'price_reduction_current' or 'price_reduction_returning'
    original_price: float
    new_price: float
    price_reduction_percent: float
    original_build_time_h: float
    new_build_time_h: float


@router.post("/generate")
def generate_notification(
    data: GenerateEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inq = db.query(Inquiry).filter(Inquiry.inquiry_id == data.inquiry_id).first()
    job = db.query(BuildJob).filter(BuildJob.job_id == data.job_id).first()

    if not inq or not job:
        raise HTTPException(status_code=404, detail="Anfrage oder Build-Job nicht gefunden")

    draft = generate_email_draft(
        notification_type=data.notification_type,
        customer_number=inq.customer_number,
        inquiry_number=inq.inquiry_number,
        order_number=inq.order_number,
        part_name=inq.part_name,
        quantity=inq.quantity,
        original_price=data.original_price,
        new_price=data.new_price,
        price_reduction_percent=data.price_reduction_percent,
        original_build_time_h=data.original_build_time_h,
        new_build_time_h=data.new_build_time_h
    )

    # Save draft to database
    notification = EmailNotification(
        customer_number=inq.customer_number,
        inquiry_number=inq.inquiry_number,
        order_number=inq.order_number,
        job_id=data.job_id,
        notification_type=data.notification_type,
        email_subject=draft["subject"],
        email_body=draft["body"],
        status="draft"
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    return {
        "notification_id": notification.notification_id,
        "subject": draft["subject"],
        "body": draft["body"]
    }


@router.get("/")
def list_notifications(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(EmailNotification)
    if status:
        query = query.filter(EmailNotification.status == status)
    notifications = query.order_by(desc(EmailNotification.generated_at)).all()

    result = []
    for n in notifications:
        result.append({
            "notification_id": n.notification_id,
            "customer_number": n.customer_number,
            "inquiry_number": n.inquiry_number,
            "order_number": n.order_number,
            "job_id": n.job_id,
            "notification_type": n.notification_type,
            "email_subject": n.email_subject,
            "email_body": n.email_body,
            "status": n.status,
            "generated_at": str(n.generated_at)
        })
    return result


@router.put("/{notification_id}/status")
def update_notification_status(
    notification_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notification = db.query(EmailNotification).filter(
        EmailNotification.notification_id == notification_id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Benachrichtigung nicht gefunden")

    if status not in ("draft", "reviewed", "sent_manually"):
        raise HTTPException(status_code=400, detail="Ungültiger Status")

    notification.status = status
    db.commit()
    return {"message": "Status aktualisiert"}
