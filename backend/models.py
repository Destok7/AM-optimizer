from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean,
    Date, DateTime, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name       = Column(String(255))
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, server_default=func.now())


class Customer(Base):
    __tablename__ = "customers"

    customer_number = Column(String(100), primary_key=True)
    created_at      = Column(DateTime, server_default=func.now())

    inquiries       = relationship("Inquiry", back_populates="customer")
    notifications   = relationship("EmailNotification", back_populates="customer")


class Inquiry(Base):
    __tablename__ = "inquiries"

    inquiry_id                  = Column(Integer, primary_key=True, autoincrement=True)
    customer_number             = Column(String(100), ForeignKey("customers.customer_number"), nullable=False)

    inquiry_number              = Column(String(100), nullable=False)
    order_number                = Column(String(100))
    inquiry_name                = Column(String(255), nullable=False)

    inquiry_date                = Column(Date, server_default=func.current_date())
    status                      = Column(String(50), default="pending")

    # Part parameters
    part_name                   = Column(String(255), nullable=False)
    quantity                    = Column(Integer, nullable=False)
    part_volume_cm3             = Column(Numeric(10, 4), nullable=False)
    stock_percent               = Column(Numeric(5, 2))
    support_volume_percent      = Column(Numeric(5, 2), nullable=False)
    part_height_mm              = Column(Numeric(8, 2), nullable=False)

    # Time parameters
    prep_time_h                 = Column(Numeric(6, 2))
    post_handling_time_h        = Column(Numeric(6, 2))
    blasting_time_h             = Column(Numeric(6, 2))
    leak_testing_time_h         = Column(Numeric(6, 2))
    qc_time_h                   = Column(Numeric(6, 2))

    # XY surface for nesting
    projected_xy_surface_cm2    = Column(Numeric(10, 4))

    # Lead time
    requested_delivery_date     = Column(Date)
    lead_time_flexible          = Column(Boolean, default=False)

    # ML model outputs
    estimated_part_price_eur    = Column(Numeric(10, 2))
    estimated_build_time_h      = Column(Numeric(8, 2))

    created_at                  = Column(DateTime, server_default=func.now())
    updated_at                  = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("inquiry_number", "part_name", name="uq_inquiry_part"),
    )

    customer        = relationship("Customer", back_populates="inquiries")
    job_links       = relationship("BuildJobInquiry", back_populates="inquiry")
    nesting_logs    = relationship("NestingLog", back_populates="inquiry")


class BuildJob(Base):
    __tablename__ = "build_jobs"

    job_id                      = Column(Integer, primary_key=True, autoincrement=True)
    job_name                    = Column(String(255), nullable=False)
    status                      = Column(String(50), default="open")

    platform_xy_surface_cm2     = Column(Numeric(10, 4), nullable=False)
    used_xy_surface_cm2         = Column(Numeric(10, 4), default=0)
    available_xy_surface_cm2    = Column(Numeric(10, 4))

    total_price_eur             = Column(Numeric(10, 2))
    total_build_time_h          = Column(Numeric(8, 2))

    planned_start_date          = Column(Date)
    planned_end_date            = Column(Date)

    created_at                  = Column(DateTime, server_default=func.now())
    updated_at                  = Column(DateTime, server_default=func.now(), onupdate=func.now())

    inquiry_links   = relationship("BuildJobInquiry", back_populates="job")
    nesting_logs    = relationship("NestingLog", back_populates="job")
    notifications   = relationship("EmailNotification", back_populates="job")


class BuildJobInquiry(Base):
    __tablename__ = "build_job_inquiries"

    id                          = Column(Integer, primary_key=True, autoincrement=True)
    job_id                      = Column(Integer, ForeignKey("build_jobs.job_id"), nullable=False)
    inquiry_id                  = Column(Integer, ForeignKey("inquiries.inquiry_id"), nullable=False)
    assigned_at                 = Column(DateTime, server_default=func.now())

    combined_part_price_eur     = Column(Numeric(10, 2))
    price_reduction_eur         = Column(Numeric(10, 2))
    price_reduction_percent     = Column(Numeric(5, 2))

    __table_args__ = (
        UniqueConstraint("job_id", "inquiry_id", name="uq_job_inquiry"),
    )

    job     = relationship("BuildJob", back_populates="inquiry_links")
    inquiry = relationship("Inquiry", back_populates="job_links")


class NestingLog(Base):
    __tablename__ = "nesting_log"

    log_id                          = Column(Integer, primary_key=True, autoincrement=True)
    job_id                          = Column(Integer, ForeignKey("build_jobs.job_id"))
    inquiry_id                      = Column(Integer, ForeignKey("inquiries.inquiry_id"))

    decision                        = Column(String(50), nullable=False)

    available_surface_before_cm2    = Column(Numeric(10, 4))
    surface_used_cm2                = Column(Numeric(10, 4))
    available_surface_after_cm2     = Column(Numeric(10, 4))

    lead_time_impact_h              = Column(Numeric(8, 2))
    gpt_reasoning_summary           = Column(Text)

    decided_at                      = Column(DateTime, server_default=func.now())

    job     = relationship("BuildJob", back_populates="nesting_logs")
    inquiry = relationship("Inquiry", back_populates="nesting_logs")


class EmailNotification(Base):
    __tablename__ = "email_notifications"

    notification_id     = Column(Integer, primary_key=True, autoincrement=True)
    customer_number     = Column(String(100), ForeignKey("customers.customer_number"), nullable=False)
    inquiry_number      = Column(String(100), nullable=False)
    order_number        = Column(String(100))
    job_id              = Column(Integer, ForeignKey("build_jobs.job_id"))

    notification_type   = Column(String(50), nullable=False)
    email_subject       = Column(Text, nullable=False)
    email_body          = Column(Text, nullable=False)

    generated_at        = Column(DateTime, server_default=func.now())
    status              = Column(String(50), default="draft")

    customer    = relationship("Customer", back_populates="notifications")
    job         = relationship("BuildJob", back_populates="notifications")
