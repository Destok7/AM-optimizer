import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base
from models import User
from routers.auth import get_password_hash
from sqlalchemy.orm import Session

# Import all routers
from routers import auth, inquiries, buildjobs, nesting, notifications, ml

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="LPBF Optimizer",
    description="Web-Plattform zur Optimierung der LPBF-Produktionsplanung",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(inquiries.router)
app.include_router(buildjobs.router)
app.include_router(nesting.router)
app.include_router(notifications.router)
app.include_router(ml.router)

# Serve frontend static files
frontend_path = os.path.join(os.path.dirname(__file__), "..", "public")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/", include_in_schema=False)
def serve_index():
    index_path = os.path.join(frontend_path, "index.html")
    return FileResponse(index_path)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "LPBF Optimizer"}


@app.on_event("startup")
def create_default_admin():
    """Creates a default admin user on first startup if no users exist."""
    db = Session(bind=engine)
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            default_user = User(
                username=os.getenv("ADMIN_USERNAME", "admin"),
                hashed_password=get_password_hash(os.getenv("ADMIN_PASSWORD", "lpbf2024!")),
                full_name="Administrator",
                is_active=True
            )
            db.add(default_user)
            db.commit()
            print("✅ Standard-Admin-Benutzer erstellt: admin / lpbf2024!")
    finally:
        db.close()
