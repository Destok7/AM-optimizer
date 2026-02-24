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


def run_migration():
    """Drop old tables and recreate with v2 schema (safe — no real data yet)."""
    with engine.connect() as conn:
        conn.execute(text("""
            DROP TABLE IF EXISTS nesting_log CASCADE;
            DROP TABLE IF EXISTS build_job_inquiries CASCADE;
            DROP TABLE IF EXISTS build_jobs CASCADE;
            DROP TABLE IF EXISTS email_notifications CASCADE;
            DROP TABLE IF EXISTS calc_parts CASCADE;
            DROP TABLE IF EXISTS combined_calculations CASCADE;
            DROP TABLE IF EXISTS parts CASCADE;
            DROP TABLE IF EXISTS inquiries CASCADE;
            DROP TABLE IF EXISTS customers CASCADE;
        """))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    print("Migration complete: all v2 tables created.")


run_migration()

app = FastAPI(title="AM-Optimizer", version="2.0")

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
