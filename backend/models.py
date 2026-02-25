from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean,
    Date, DateTime, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

MACHINE_MATERIALS = {
    "Xline":  ["AlSi10Mg"],
    "EOS":    ["AlSi10Mg", "IN718", "IN625"],
    "M2_alt": ["IN718", "IN625", "1.4404"],
    "M2_neu": ["AlSi10Mg", "IN718", "IN625", "1.4404"],
}

MACHINE_PLATFORM_MM2 = {
    "Xline":  320000,
    "EOS":    62500,
    "M2_alt": 62500,
    "M2_neu": 48400,
}

def get_material_group(material: str) -> str:
    if material in ("IN718", "IN625"):
        return "IN718_IN625"
    return material


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
    inquiry_id      = Column(Integer, primary_key=True, autoincrement=True)
    inquiry_number  = Column(String(100), nullable=False)
    order_number    = Column(String(100))
    customer_number = Column(String(100), ForeignKey("customers.customer_number"), nullable=False)
    inquiry_date    = Column(Date, server_default=func.current_date())
    order_date      = Column(Date)
    requested_delivery_date = Column(Date)
    status          = Column(String(50), default="Anfrage")
    machine         = Column(String(50), nullable=False)
    # Bauzeit belongs to the entire build job, not individual parts
    manual_build_time_h = Column(Numeric(8, 2))
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())
    customer        = relationship("Customer", back_populates="inquiries")
    parts           = relationship("Part", back_populates="inquiry", cascade="all, delete-orphan")


class Part(Base):
    __tablename__ = "parts"
    part_id                  = Column(Integer, primary_key=True, autoincrement=True)
    inquiry_id               = Column(Integer, ForeignKey("inquiries.inquiry_id", ondelete="CASCADE"), nullable=False)
    material                 = Column(String(50), nullable=False)
    part_name                = Column(String(255), nullable=False)
    quantity                 = Column(Integer, nullable=False, default=1)
    part_volume_cm3          = Column(Numeric(12, 4), nullable=False)  # [cm³]
    aufmass_pct              = Column(Numeric(8, 2))   # Aufmaß [%]
    support_volume_cm3       = Column(Numeric(10, 4), nullable=False)
    part_height_mm           = Column(Numeric(8, 2), nullable=False)
    prep_time_min            = Column(Numeric(8, 2))
    post_handling_time_min   = Column(Numeric(8, 2))
    blasting_time_min        = Column(Numeric(8, 2))
    leak_testing_time_min    = Column(Numeric(8, 2))
    qc_time_min              = Column(Numeric(8, 2))
    projected_xy_surface_mm2 = Column(Numeric(12, 2))
    manual_part_price_eur    = Column(Numeric(10, 2))
    # manual_build_time_h removed — now on Inquiry level
    created_at               = Column(DateTime, server_default=func.now())
    updated_at               = Column(DateTime, server_default=func.now(), onupdate=func.now())
    inquiry    = relationship("Inquiry", back_populates="parts")
    calc_links = relationship("CalcPart", back_populates="part")


class CombinedCalculation(Base):
    __tablename__ = "combined_calculations"
    calc_id              = Column(Integer, primary_key=True, autoincrement=True)
    calc_number          = Column(String(100), unique=True, nullable=False)
    calc_name            = Column(String(255), nullable=False)
    machine              = Column(String(50), nullable=False)
    material_group       = Column(String(50), nullable=False)
    platform_surface_mm2 = Column(Numeric(12, 2), nullable=False)
    start_date           = Column(Date)
    end_date             = Column(Date)
    status               = Column(String(50), default="open")
    created_at           = Column(DateTime, server_default=func.now())
    updated_at           = Column(DateTime, server_default=func.now(), onupdate=func.now())
    calc_parts           = relationship("CalcPart", back_populates="calculation", cascade="all, delete-orphan")
    notifications        = relationship("EmailNotification", back_populates="calculation")


class CalcPart(Base):
    """One row per part selected for a combined calculation.
    Override columns allow editing part parameters within the calculation
    without modifying the original data in the Datenbank."""
    __tablename__ = "calc_parts"
    id                      = Column(Integer, primary_key=True, autoincrement=True)
    calc_id                 = Column(Integer, ForeignKey("combined_calculations.calc_id", ondelete="CASCADE"), nullable=False)
    part_id                 = Column(Integer, ForeignKey("parts.part_id"), nullable=False)

    # Identity overrides
    material_override       = Column(String(50))
    quantity_override       = Column(Integer)

    # Parameter overrides (when set, used instead of original part values for regression)
    part_volume_cm3_override        = Column(Numeric(12, 4))
    aufmass_pct_override            = Column(Numeric(8, 2))
    support_volume_cm3_override     = Column(Numeric(10, 4))
    part_height_mm_override         = Column(Numeric(8, 2))
    prep_time_min_override          = Column(Numeric(8, 2))
    post_handling_time_min_override = Column(Numeric(8, 2))
    blasting_time_min_override      = Column(Numeric(8, 2))
    leak_testing_time_min_override  = Column(Numeric(8, 2))
    qc_time_min_override            = Column(Numeric(8, 2))

    # Regression results
    calc_part_price_eur     = Column(Numeric(10, 2))
    calc_build_time_h       = Column(Numeric(8, 2))
    price_reduction_eur     = Column(Numeric(10, 2))
    price_reduction_percent = Column(Numeric(5, 2))

    __table_args__ = (UniqueConstraint("calc_id", "part_id", name="uq_calc_part"),)
    calculation = relationship("CombinedCalculation", back_populates="calc_parts")
    part        = relationship("Part", back_populates="calc_links")


class EmailNotification(Base):
    __tablename__ = "email_notifications"
    notification_id     = Column(Integer, primary_key=True, autoincrement=True)
    calc_id             = Column(Integer, ForeignKey("combined_calculations.calc_id"))
    customer_number     = Column(String(100), ForeignKey("customers.customer_number"), nullable=False)
    inquiry_number      = Column(String(100), nullable=False)
    order_number        = Column(String(100))
    notification_type   = Column(String(50), nullable=False)
    email_subject       = Column(Text, nullable=False)
    email_body          = Column(Text, nullable=False)
    status              = Column(String(50), default="draft")
    generated_at        = Column(DateTime, server_default=func.now())
    customer    = relationship("Customer", back_populates="notifications")
    calculation = relationship("CombinedCalculation", back_populates="notifications")
