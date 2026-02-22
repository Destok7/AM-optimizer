from sqlalchemy.orm import Session
from sqlalchemy import and_
from decimal import Decimal
from models import Inquiry, BuildJob, BuildJobInquiry, NestingLog


def run_nesting_algorithm(job_id: int, db: Session) -> dict:
    """
    Core nesting algorithm.
    Finds all pending inquiries with a projected XY surface that fits
    in the available space of the given build job, and assigns them.
    """
    job = db.query(BuildJob).filter(BuildJob.job_id == job_id).first()
    if not job:
        return {"error": "Build-Job nicht gefunden"}

    if job.status not in ("open", "planned"):
        return {"error": "Build-Job ist nicht offen für Nesting"}

    available_surface = float(job.available_xy_surface_cm2 or job.platform_xy_surface_cm2)

    # Find pending inquiries with a defined XY surface that are not yet assigned to this job
    already_assigned_ids = [
        link.inquiry_id
        for link in db.query(BuildJobInquiry).filter(BuildJobInquiry.job_id == job_id).all()
    ]

    candidates = db.query(Inquiry).filter(
        and_(
            Inquiry.status == "pending",
            Inquiry.projected_xy_surface_cm2 != None,
            ~Inquiry.inquiry_id.in_(already_assigned_ids) if already_assigned_ids else True
        )
    ).order_by(Inquiry.projected_xy_surface_cm2.desc()).all()

    nested = []
    rejected_no_space = []
    rejected_no_surface = []

    for inq in candidates:
        required = float(inq.projected_xy_surface_cm2) * inq.quantity

        if required <= available_surface:
            surface_before = available_surface

            # Assign to job
            link = BuildJobInquiry(
                job_id=job_id,
                inquiry_id=inq.inquiry_id
            )
            db.add(link)

            # Update inquiry status
            inq.status = "combined"

            # Update available surface
            available_surface -= required
            used = float(job.used_xy_surface_cm2 or 0) + required
            job.used_xy_surface_cm2 = used
            job.available_xy_surface_cm2 = available_surface

            # Log decision
            log = NestingLog(
                job_id=job_id,
                inquiry_id=inq.inquiry_id,
                decision="nested",
                available_surface_before_cm2=surface_before,
                surface_used_cm2=required,
                available_surface_after_cm2=available_surface
            )
            db.add(log)
            nested.append({
                "inquiry_id": inq.inquiry_id,
                "inquiry_name": inq.inquiry_name,
                "surface_used_cm2": required,
                "available_after_cm2": available_surface
            })
        else:
            # Log rejection
            log = NestingLog(
                job_id=job_id,
                inquiry_id=inq.inquiry_id,
                decision="rejected_no_space",
                available_surface_before_cm2=available_surface,
                surface_used_cm2=required,
                available_surface_after_cm2=available_surface
            )
            db.add(log)
            rejected_no_space.append({
                "inquiry_id": inq.inquiry_id,
                "inquiry_name": inq.inquiry_name,
                "required_cm2": required,
                "available_cm2": available_surface
            })

    # Recalculate total build time (sum of all assigned inquiries' estimated build times)
    all_links = db.query(BuildJobInquiry).filter(BuildJobInquiry.job_id == job_id).all()
    total_time = 0
    total_price = 0
    for link in all_links:
        inq = db.query(Inquiry).filter(Inquiry.inquiry_id == link.inquiry_id).first()
        if inq:
            if inq.estimated_build_time_h:
                total_time = max(total_time, float(inq.estimated_build_time_h))
            if inq.estimated_part_price_eur:
                total_price += float(inq.estimated_part_price_eur) * inq.quantity

    job.total_build_time_h = total_time
    job.total_price_eur = total_price

    db.commit()

    return {
        "job_id": job_id,
        "job_name": job.job_name,
        "nested_count": len(nested),
        "rejected_count": len(rejected_no_space),
        "available_surface_remaining_cm2": available_surface,
        "fill_percent": round(
            float(job.used_xy_surface_cm2 or 0) / float(job.platform_xy_surface_cm2) * 100, 1
        ),
        "nested": nested,
        "rejected_no_space": rejected_no_space
    }
