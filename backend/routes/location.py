"""
GigShield — Live Location & Risk Routes
POST /api/location/update   — update worker location + compute live risk
GET  /api/risk/live         — get current risk score with weather
POST /api/risk/scan         — manual AI scan (triggers background task)
"""
import json
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.db       import db, row_to_dict, now_iso, audit
from services.logic    import get_weather
from services.auth_deps import get_current_worker, require_kyc
from ai.risk_model     import compute_risk_score, score_from_weather
from ai.trigger        import run_auto_trigger_for_worker

router = APIRouter()


class LocationUpdate(BaseModel):
    latitude:  float
    longitude: float
    city:      Optional[str] = None
    zone:      Optional[str] = None


@router.post("/location/update", summary="Update worker live location + trigger AI risk scan")
async def update_location(
    req: LocationUpdate,
    bg:  BackgroundTasks,
    w:   dict = Depends(require_kyc),
):
    loc_str = json.dumps({"lat": req.latitude, "lon": req.longitude})

    with db() as conn:
        # Update worker last location
        conn.execute(
            "UPDATE workers SET last_location=? WHERE id=?",
            (loc_str, w["id"])
        )
        # Update active shift location
        conn.execute(
            """UPDATE shifts SET latitude=?,longitude=?,location_city=?
               WHERE worker_id=? AND status='ACTIVE'""",
            (req.latitude, req.longitude, req.city or w["city"], w["id"])
        )

    # Fire background AI scan
    bg.add_task(run_auto_trigger_for_worker, w["id"])

    # Immediate weather + risk for response
    weather = await get_weather(req.city or w["city"])
    risk    = compute_risk_score(
        zone    = req.zone or w.get("zone", "Unknown"),
        city    = req.city or w["city"],
        rain_mm = weather["rain_mm"],
        temp_c  = weather["temp_c"],
        aqi     = weather["aqi"],
    )

    return {
        "success":   True,
        "location":  {"lat": req.latitude, "lon": req.longitude},
        "weather":   weather,
        "risk":      risk,
        "message":   "Location updated. AI risk scan running in background.",
    }


@router.get("/risk/live", summary="Get live risk score with current weather")
async def get_live_risk(w: dict = Depends(get_current_worker)):
    weather = await get_weather(w["city"])
    with db() as conn:
        shift    = row_to_dict(conn.execute(
            "SELECT * FROM shifts WHERE worker_id=? AND status='ACTIVE'", (w["id"],)).fetchone())
        wk_claims = conn.execute(
            "SELECT COUNT(*) as c FROM claims WHERE worker_id=? AND week_id=? AND status IN ('APPROVED','PAID')",
            (w["id"], __import__('services.db', fromlist=['cur_week']).cur_week())).fetchone()["c"]

    risk = compute_risk_score(
        zone             = w.get("zone", "Unknown"),
        city             = w["city"],
        rain_mm          = weather["rain_mm"],
        temp_c           = weather["temp_c"],
        aqi              = weather["aqi"],
        shift_hours      = (shift.get("active_minutes") or 0) / 60 if shift else 0,
        claims_this_week = wk_claims,
    )

    return {
        "worker_id":    w["id"],
        "shift_active": bool(shift),
        "weather":      weather,
        "risk":         risk,
        "live_score":   risk["risk_score"],
    }


@router.post("/risk/scan", summary="Manual AI risk scan — auto-triggers claim if threshold met")
async def manual_risk_scan(
    bg: BackgroundTasks,
    w:  dict = Depends(require_kyc),
):
    bg.add_task(run_auto_trigger_for_worker, w["id"])
    return {
        "success": True,
        "message": "AI risk scan queued. Claims will auto-generate if thresholds are crossed.",
    }
