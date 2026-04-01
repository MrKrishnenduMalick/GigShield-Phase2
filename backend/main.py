"""
GigShield v5.0 — Single Command Startup
Serves BOTH backend API and frontend from one process.

Run:
    python main.py
    OR
    uvicorn main:app --reload --port 8000

Open: http://localhost:8000
API:  http://localhost:8000/docs
"""
import os, uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from services.db import init_db, migrate_db
from routes.auth     import router as auth_router
from routes.kyc      import router as kyc_router
from routes.worker   import router as worker_router
from routes.shifts   import router as shift_router
from routes.claims   import router as claim_router
from routes.payout   import router as payout_router
from routes.admin    import router as admin_router
from routes.weather  import router as weather_router
from routes.location import router as location_router

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title       = "GigShield API",
    description = "AI-Powered Parametric Micro-Insurance for Gig Delivery Workers",
    version     = "5.0.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ── API Routes ────────────────────────────────────────────────
app.include_router(auth_router,     prefix="/api/auth",     tags=["Auth"])
app.include_router(kyc_router,      prefix="/api/kyc",      tags=["KYC"])
app.include_router(worker_router,   prefix="/api",          tags=["Worker"])
app.include_router(shift_router,    prefix="/api/shifts",   tags=["Shifts"])
app.include_router(claim_router,    prefix="/api/claims",   tags=["Claims"])
app.include_router(payout_router,   prefix="/api/payout",   tags=["Payouts"])
app.include_router(admin_router,    prefix="/api/admin",    tags=["Admin"])
app.include_router(weather_router,  prefix="/api/weather",  tags=["Weather"])
app.include_router(location_router, prefix="/api",          tags=["Location & Risk"])

# ── Health ────────────────────────────────────────────────────
@app.get("/api/health", tags=["Health"])
def health():
    from services.db import db
    with db() as conn:
        return {
            "status":   "ok",
            "version":  "5.0.0",
            "workers":  conn.execute("SELECT COUNT(*) as c FROM workers").fetchone()["c"],
            "claims":   conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"],
            "payouts":  conn.execute("SELECT COUNT(*) as c FROM payouts").fetchone()["c"],
        }

# ── Serve Frontend (SPA fallback) ─────────────────────────────
FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")
FRONTEND = os.path.abspath(FRONTEND)

if os.path.exists(FRONTEND):
    # Serve static assets
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str = ""):
        # Don't intercept API or docs routes
        if full_path.startswith(("api/", "docs", "redoc", "openapi")):
            from fastapi import HTTPException
            raise HTTPException(404)
        index = os.path.join(FRONTEND, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return {"message": "Frontend not found — place index.html in frontend/"}

# ── Startup ───────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()
    migrate_db()
    print("\n" + "="*55)
    print("  GigShield v5.0 — Running!")
    print("="*55)
    print("  App:       http://localhost:8000")
    print("  API Docs:  http://localhost:8000/docs")
    print("  Admin:     http://localhost:8000/api/admin/stats?admin=admin2026")
    print("  Database:  gigshield.db (open with sqlitebrowser)")
    print("="*55 + "\n")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
