import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import engine, Base, SessionLocal
from models import User
from routers.auth import get_password_hash
from routers import auth
from routers.datenbank import router as datenbank_router
from routers.kalkulation import router as kalkulation_router
from routers.emails import router as emails_router
from routers.ml import router as ml_router


def col_exists(conn, table, column):
    r = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column}).fetchone()
    return r is not None


def run_migration():
    """Smart migration — rename columns and add missing ones without losing data."""
    with engine.connect() as conn:
        # Drop old v1 tables if present
        conn.execute(text("DROP TABLE IF EXISTS nesting_log CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS build_job_inquiries CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS build_jobs CASCADE"))

        # parts: part_volume_mm3 → part_volume_cm3
        if col_exists(conn, "parts", "part_volume_mm3"):
            conn.execute(text("ALTER TABLE parts RENAME COLUMN part_volume_mm3 TO part_volume_cm3"))

        # parts: stock_cm3 → aufmass_pct
        if col_exists(conn, "parts", "stock_cm3"):
            conn.execute(text("ALTER TABLE parts RENAME COLUMN stock_cm3 TO aufmass_pct"))

        # parts: remove manual_build_time_h (moved to inquiries)
        if col_exists(conn, "parts", "manual_build_time_h"):
            conn.execute(text("ALTER TABLE parts DROP COLUMN manual_build_time_h"))

        # inquiries: add manual_build_time_h if missing
        if not col_exists(conn, "inquiries", "manual_build_time_h"):
            conn.execute(text("ALTER TABLE inquiries ADD COLUMN manual_build_time_h NUMERIC(8,2)"))

        # calc_parts: part_volume_mm3_override → part_volume_cm3_override
        if col_exists(conn, "calc_parts", "part_volume_mm3_override"):
            conn.execute(text("ALTER TABLE calc_parts RENAME COLUMN part_volume_mm3_override TO part_volume_cm3_override"))

        # calc_parts: stock_cm3_override → aufmass_pct_override
        if col_exists(conn, "calc_parts", "stock_cm3_override"):
            conn.execute(text("ALTER TABLE calc_parts RENAME COLUMN stock_cm3_override TO aufmass_pct_override"))

        conn.commit()

    # Create any still-missing tables (safe — skips existing ones)
    Base.metadata.create_all(bind=engine)
    print("Migration v2.1 complete.")


run_migration()

app = FastAPI(title="AM-Optimizer", version="2.1")

app.include_router(auth.router)
app.include_router(datenbank_router)
app.include_router(kalkulation_router)
app.include_router(emails_router)
app.include_router(ml_router)

app.mount("/static", StaticFiles(directory="../public"), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def serve_index():
    return FileResponse("../public/index.html")


@app.get("/{page}.html")
def serve_page(page: str):
    path = f"../public/{page}.html"
    if os.path.exists(path):
        return FileResponse(path)
    return FileResponse("../public/index.html")


@app.on_event("startup")
def create_default_admin():
    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(
            User.username == os.getenv("ADMIN_USERNAME", "admin")
        ).first()
        if not existing:
            admin = User(
                username=os.getenv("ADMIN_USERNAME", "admin"),
                hashed_password=get_password_hash(os.getenv("ADMIN_PASSWORD", "admin123")),
                full_name="Administrator",
                is_active=True,
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()
