from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from pydantic import BaseModel
from decimal import Decimal
from datetime import date
from database import get_db
from models import BuildJob, BuildJobInquiry, Inquiry, User
from routers.auth import get_current_user

router = APIRouter(prefix="/api/buildjobs", tags=["buildjobs"])


class BuildJobCreate(BaseModel):
    job_name: str
    platform_xy_surface_cm2: Decimal
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None


class BuildJobUpdate(BaseModel):
    status: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None


@router.post("/")
def create_build_job(
    data: BuildJobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = BuildJob(
        job_name=data.job_name,
        platform_xy_surface_cm2=data.platform_xy_surface_cm2,
        available_xy_surface_cm2=data.platform_xy_surface_cm2,
        used_xy_surface_cm2=0,
        planned_start_date=data.planned_start_date,
        planned_end_date=data.planned_end_date
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"message": "Build-Job erstellt", "job_id": job.job_id}


@router.get("/")
def list_build_jobs(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(BuildJob)
    if status:
        query = query.filter(BuildJob.status == status)
    jobs = query.order_by(desc(BuildJob.created_at)).all()

    result = []
    for job in jobs:
        # Count assigned inquiries
        inquiry_count = db.query(BuildJobInquiry).filter(BuildJobInquiry.job_id == job.job_id).count()
        fill_percent = 0
        if job.platform_xy_surface_cm2 and float(job.platform_xy_surface_cm2) > 0:
            fill_percent = round(
                float(job.used_xy_surface_cm2 or 0) / float(job.platform_xy_surface_cm2) * 100, 1
            )
        result.append({
            "job_id": job.job_id,
            "job_name": job.job_name,
            "status": job.status,
            "platform_xy_surface_cm2": float(job.platform_xy_surface_cm2),
            "used_xy_surface_cm2": float(job.used_xy_surface_cm2 or 0),
            "available_xy_surface_cm2": float(job.available_xy_surface_cm2 or 0),
            "fill_percent": fill_percent,
            "total_price_eur": float(job.total_price_eur) if job.total_price_eur else None,
            "total_build_time_h": float(job.total_build_time_h) if job.total_build_time_h else None,
            "planned_start_date": str(job.planned_start_date) if job.planned_start_date else None,
            "planned_end_date": str(job.planned_end_date) if job.planned_end_date else None,
            "inquiry_count": inquiry_count,
            "created_at": str(job.created_at)
        })
    return result


@router.get("/{job_id}")
def get_build_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = db.query(BuildJob).filter(BuildJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Build-Job nicht gefunden")

    # Get all assigned inquiries
    links = db.query(BuildJobInquiry).filter(BuildJobInquiry.job_id == job_id).all()
    assigned_inquiries = []
    for link in links:
        inq = db.query(Inquiry).filter(Inquiry.inquiry_id == link.inquiry_id).first()
        if inq:
            assigned_inquiries.append({
                "inquiry_id": inq.inquiry_id,
                "inquiry_name": inq.inquiry_name,
                "inquiry_number": inq.inquiry_number,
                "customer_number": inq.customer_number,
                "part_name": inq.part_name,
                "quantity": inq.quantity,
                "projected_xy_surface_cm2": float(inq.projected_xy_surface_cm2) if inq.projected_xy_surface_cm2 else None,
                "combined_part_price_eur": float(link.combined_part_price_eur) if link.combined_part_price_eur else None,
                "price_reduction_percent": float(link.price_reduction_percent) if link.price_reduction_percent else None,
            })

    return {
        "job_id": job.job_id,
        "job_name": job.job_name,
        "status": job.status,
        "platform_xy_surface_cm2": float(job.platform_xy_surface_cm2),
        "used_xy_surface_cm2": float(job.used_xy_surface_cm2 or 0),
        "available_xy_surface_cm2": float(job.available_xy_surface_cm2 or 0),
        "total_price_eur": float(job.total_price_eur) if job.total_price_eur else None,
        "total_build_time_h": float(job.total_build_time_h) if job.total_build_time_h else None,
        "planned_start_date": str(job.planned_start_date) if job.planned_start_date else None,
        "planned_end_date": str(job.planned_end_date) if job.planned_end_date else None,
        "assigned_inquiries": assigned_inquiries
    }


@router.put("/{job_id}")
def update_build_job(
    job_id: int,
    data: BuildJobUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = db.query(BuildJob).filter(BuildJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Build-Job nicht gefunden")

    for field, value in data.dict(exclude_unset=True).items():
        setattr(job, field, value)

    db.commit()
    return {"message": "Build-Job aktualisiert"}
