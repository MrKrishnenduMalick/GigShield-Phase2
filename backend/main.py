"""
GigShield v6.0 — Hackathon-Winning MVP
Run:  python main.py
Docs: http://localhost:8000/docs
"""
import os, uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from services.db import init_db, migrate_db
from routes.auth      import router as auth_router
from routes.kyc       import router as kyc_router
from routes.worker    import router as worker_router
from routes.shifts    import router as shift_router
from routes.claims    import router as claim_router
from routes.payout    import router as payout_router
from routes.admin     import router as admin_router
from routes.weather   import router as weather_router
from routes.location  import router as location_router
from routes.demo      import router as demo_router
from routes.analytics import router as analytics_router

app = FastAPI(
    title="GigShield API v6",
    description="AI-Powered Parametric Micro-Insurance — Hackathon MVP",
    version="6.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router,      prefix="/api/auth",      tags=["Auth"])
app.include_router(kyc_router,       prefix="/api/kyc",       tags=["KYC"])
app.include_router(worker_router,    prefix="/api",           tags=["Worker"])
app.include_router(shift_router,     prefix="/api/shifts",    tags=["Shifts"])
app.include_router(claim_router,     prefix="/api/claims",    tags=["Claims"])
app.include_router(payout_router,    prefix="/api/payout",    tags=["Payouts"])
app.include_router(admin_router,     prefix="/api/admin",     tags=["Admin"])
app.include_router(weather_router,   prefix="/api/weather",   tags=["Weather"])
app.include_router(location_router,  prefix="/api",           tags=["Location"])
app.include_router(demo_router,      prefix="/api",           tags=["Demo"])
app.include_router(analytics_router, prefix="/api/admin",     tags=["Analytics"])

@app.get("/api/health", tags=["Health"])
def health():
    from services.db import db
    from ml.model import get_model_status
    with db() as conn:
        return {
            "status": "ok", "version": "6.0.0",
            "workers": conn.execute("SELECT COUNT(*) as c FROM workers").fetchone()["c"],
            "claims":  conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"],
            "ml":      get_model_status(),
        }

@app.get("/api/ml/status", tags=["ML"])
def ml_status():
    from ml.model import get_model_status
    return get_model_status()

@app.post("/api/ml/predict", tags=["ML"])
def ml_predict(rain_mm: float=0, temp_c: float=30, aqi: int=80,
               city: str="Mumbai", zone: str="Bandra"):
    from ml.model import predict_disruption_probability, predict_weekly_earnings, compute_dynamic_premium
    return {
        "risk":     predict_disruption_probability(rain_mm, temp_c, aqi, city, zone),
        "earnings": predict_weekly_earnings(city, zone, rain_mm, temp_c, aqi),
        "premium":  compute_dynamic_premium("Standard", zone, city, rain_mm, temp_c, aqi),
    }

# Serve frontend
FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(FRONTEND):
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str = ""):
        if full_path.startswith(("api/","docs","redoc","openapi")):
            from fastapi import HTTPException; raise HTTPException(404)
        idx = os.path.join(FRONTEND, "index.html")
        return FileResponse(idx) if os.path.exists(idx) else {"error": "Frontend not found"}

@app.on_event("startup")
def startup():
    init_db()
    migrate_db()
    # Train ML models
    from ml.model import train_models
    train_models()
    print("\n" + "="*55)
    print("  GigShield v6.0 — Hackathon MVP")
    print("="*55)
    print("  App:      http://localhost:8000")
    print("  Docs:     http://localhost:8000/docs")
    print("  Demo:     POST /api/demo/instant")
    print("  ML:       GET  /api/ml/status")
    print("="*55 + "\n")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
