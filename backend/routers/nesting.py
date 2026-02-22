from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from models import NestingLog, Inquiry, BuildJob, User
from routers.auth import get_current_user
from services.nesting_engine import run_nesting_algorithm
from services.gpt_service import evaluate_lead_time

router = APIRouter(prefix="/api/nesting", tags=["nesting"])


@router.post("/run/{job_id}")
def trigger_nesting(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = run_nesting_algorithm(job_id, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/log")
def get_nesting_log(
    job_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(NestingLog)
    if job_id:
        query = query.filter(NestingLog.job_id == job_id)
    logs = query.order_by(desc(NestingLog.decided_at)).limit(200).all()

    result = []
    for log in logs:
        inq = db.query(Inquiry).filter(Inquiry.inquiry_id == log.inquiry_id).first()
        job = db.query(BuildJob).filter(BuildJob.job_id == log.job_id).first()
        result.append({
            "log_id": log.log_id,
            "job_id": log.job_id,
            "job_name": job.job_name if job else None,
            "inquiry_id": log.inquiry_id,
            "inquiry_name": inq.inquiry_name if inq else None,
            "decision": log.decision,
            "available_surface_before_cm2": float(log.available_surface_before_cm2) if log.available_surface_before_cm2 else None,
            "surface_used_cm2": float(log.surface_used_cm2) if log.surface_used_cm2 else None,
            "available_surface_after_cm2": float(log.available_surface_after_cm2) if log.available_surface_after_cm2 else None,
            "lead_time_impact_h": float(log.lead_time_impact_h) if log.lead_time_impact_h else None,
            "gpt_reasoning_summary": log.gpt_reasoning_summary,
            "decided_at": str(log.decided_at)
        })
    return result


@router.post("/evaluate-lead-time/{inquiry_id}/{job_id}")
def evaluate_inquiry_lead_time(
    inquiry_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inq = db.query(Inquiry).filter(Inquiry.inquiry_id == inquiry_id).first()
    job = db.query(BuildJob).filter(BuildJob.job_id == job_id).first()

    if not inq or not job:
        raise HTTPException(status_code=404, detail="Anfrage oder Build-Job nicht gefunden")

    reasoning = evaluate_lead_time(
        inquiry_name=inq.inquiry_name,
        customer_number=inq.customer_number,
        requested_delivery_date=str(inq.requested_delivery_date) if inq.requested_delivery_date else None,
        lead_time_flexible=inq.lead_time_flexible or False,
        current_build_time_h=float(inq.estimated_build_time_h or 0),
        combined_build_time_h=float(job.total_build_time_h or 0)
    )

    # Store GPT reasoning in the latest nesting log entry for this pair
    log = db.query(NestingLog).filter(
        NestingLog.inquiry_id == inquiry_id,
        NestingLog.job_id == job_id
    ).order_by(desc(NestingLog.decided_at)).first()

    if log:
        log.gpt_reasoning_summary = reasoning
        db.commit()

    return {"reasoning": reasoning}
