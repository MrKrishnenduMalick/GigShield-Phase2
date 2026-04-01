"""
GigShield Analytics — Admin dashboard data
Loss ratio, risk heatmap, weekly trends, predictions
"""

import os, json
from fastapi import APIRouter
from services.db import db, rows_to_list, row_to_dict, cur_week, ZONE_RISK, CITY_SEASONAL
from ml.model import predict_disruption_probability, get_model_status

router   = APIRouter()
ADMIN_SK = os.getenv("ADMIN_SECRET", "admin2026")

def _chk(admin: str):
    from fastapi import HTTPException
    if admin != ADMIN_SK: raise HTTPException(403, "Invalid admin secret")


@router.get("/analytics/overview")
def analytics_overview(admin: str = ""):
    _chk(admin)
    with db() as conn:
        workers  = conn.execute("SELECT COUNT(*) as c FROM workers").fetchone()["c"]
        kyc_v    = conn.execute("SELECT COUNT(*) as c FROM kyc WHERE status='VERIFIED'").fetchone()["c"]
        claims_t = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
        claims_p = conn.execute("SELECT COUNT(*) as c FROM claims WHERE status='PAID'").fetchone()["c"]
        claims_b = conn.execute("SELECT COUNT(*) as c FROM claims WHERE status='BLOCKED'").fetchone()["c"]
        total_disbursed = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM payouts").fetchone()["s"]
        total_premiums  = conn.execute("SELECT COALESCE(SUM(dynamic_premium),0) as s FROM policies WHERE status='ACTIVE'").fetchone()["s"]
        active_shifts   = conn.execute("SELECT COUNT(*) as c FROM shifts WHERE status='ACTIVE'").fetchone()["c"]
        week_claims     = conn.execute("SELECT COUNT(*) as c FROM claims WHERE week_id=?", (cur_week(),)).fetchone()["c"]
        week_paid_amt   = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM payouts WHERE week_id=?", (cur_week(),)).fetchone()["s"]

    premium_pool  = total_premiums * 10  # weekly pool estimate
    loss_ratio    = round(total_disbursed / max(premium_pool, 1) * 100, 1)

    return {
        "workers":         workers,
        "kyc_verified":    kyc_v,
        "active_shifts":   active_shifts,
        "total_claims":    claims_t,
        "paid_claims":     claims_p,
        "blocked_claims":  claims_b,
        "total_disbursed": round(total_disbursed, 2),
        "premium_pool":    round(premium_pool, 2),
        "loss_ratio":      loss_ratio,
        "loss_ratio_status": "HEALTHY" if loss_ratio < 65 else "WARNING" if loss_ratio < 80 else "CRITICAL",
        "week_claims":     week_claims,
        "week_paid_amt":   round(week_paid_amt, 2),
        "model_status":    get_model_status(),
    }


@router.get("/analytics/risk-heatmap")
def risk_heatmap(admin: str = ""):
    _chk(admin)
    # Generate heatmap data for all zones
    zones = [
        {"zone": "Bandra",          "city": "Mumbai",    "lat": 19.054, "lon": 72.840},
        {"zone": "Andheri",         "city": "Mumbai",    "lat": 19.119, "lon": 72.848},
        {"zone": "Dharavi",         "city": "Mumbai",    "lat": 19.041, "lon": 72.853},
        {"zone": "Salt Lake",       "city": "Kolkata",   "lat": 22.578, "lon": 88.420},
        {"zone": "T Nagar",         "city": "Chennai",   "lat": 13.038, "lon": 80.234},
        {"zone": "Koramangala",     "city": "Bangalore", "lat": 12.935, "lon": 77.616},
        {"zone": "Whitefield",      "city": "Bangalore", "lat": 12.969, "lon": 77.750},
        {"zone": "Connaught Place", "city": "Delhi",     "lat": 28.631, "lon": 77.219},
        {"zone": "Dwarka",          "city": "Delhi",     "lat": 28.558, "lon": 77.045},
        {"zone": "Sector 18",       "city": "Noida",     "lat": 28.570, "lon": 77.321},
        {"zone": "Jubilee Hills",   "city": "Hyderabad", "lat": 17.431, "lon": 78.408},
    ]

    from services.db import MOCK_WEATHER
    result = []
    for z in zones:
        w   = MOCK_WEATHER.get(z["city"], {"rain_mm":5,"temp_c":30,"aqi":100})
        r   = predict_disruption_probability(w["rain_mm"], w["temp_c"], w["aqi"], z["city"], z["zone"])
        zr  = ZONE_RISK.get(z["zone"], 1.0)

        with db() as conn:
            claims_here = conn.execute(
                "SELECT COUNT(*) as c FROM claims cl JOIN workers w ON cl.worker_id=w.id WHERE w.zone=? AND cl.week_id=?",
                (z["zone"], cur_week())).fetchone()["c"]

        result.append({
            **z,
            "risk_score":   r["risk_score"],
            "risk_level":   r["risk_level"],
            "zone_risk_factor": zr,
            "disruption_prob":  r["probability"],
            "claims_this_week": claims_here,
            "weather":      {"rain_mm": w["rain_mm"], "temp_c": w["temp_c"], "aqi": w["aqi"]},
            "intensity":    round(r["risk_score"] / 100, 3),
        })

    return {
        "heatmap":    sorted(result, key=lambda x: x["risk_score"], reverse=True),
        "highest_risk": result[0]["zone"] if result else "—",
        "avg_risk":   round(sum(z["risk_score"] for z in result) / len(result), 1),
    }


@router.get("/analytics/weekly-trend")
def weekly_trend(admin: str = ""):
    _chk(admin)
    with db() as conn:
        # Last 8 weeks of claims
        rows = rows_to_list(conn.execute("""
            SELECT week_id,
                   COUNT(*) as claims,
                   COALESCE(SUM(amount),0) as paid,
                   COUNT(CASE WHEN status='BLOCKED' THEN 1 END) as blocked
            FROM claims
            GROUP BY week_id
            ORDER BY week_id DESC
            LIMIT 8
        """).fetchall())

        # Trigger breakdown
        triggers = rows_to_list(conn.execute("""
            SELECT trigger_type, COUNT(*) as count, COALESCE(SUM(amount),0) as total
            FROM claims WHERE status IN ('PAID','APPROVED')
            GROUP BY trigger_type
            ORDER BY count DESC
        """).fetchall())

        # Top zones by claims
        top_zones = rows_to_list(conn.execute("""
            SELECT w.zone, COUNT(*) as claims, COALESCE(SUM(c.amount),0) as paid
            FROM claims c JOIN workers w ON c.worker_id=w.id
            GROUP BY w.zone ORDER BY claims DESC LIMIT 5
        """).fetchall())

    return {
        "weekly_trend":    list(reversed(rows)),
        "trigger_breakdown": triggers,
        "top_zones":       top_zones,
        "current_week":    cur_week(),
    }


@router.get("/analytics/predictions")
def weekly_predictions(admin: str = ""):
    _chk(admin)
    from services.db import MOCK_WEATHER

    cities = ["Mumbai","Delhi","Kolkata","Bangalore","Chennai","Hyderabad"]
    predictions = []
    for city in cities:
        w    = MOCK_WEATHER.get(city, {"rain_mm":5,"temp_c":30,"aqi":100})
        r    = predict_disruption_probability(w["rain_mm"], w["temp_c"], w["aqi"], city=city)
        earn = predict_disruption_probability(w["rain_mm"], w["temp_c"], w["aqi"], city=city)
        predictions.append({
            "city":            city,
            "risk_next_week":  r["risk_score"],
            "disruption_prob": r["probability"],
            "weather":         w,
            "recommendation":  r["recommendation"],
        })

    return {
        "predictions":    sorted(predictions, key=lambda x: x["risk_next_week"], reverse=True),
        "highest_risk_city": predictions[0]["city"] if predictions else "—",
        "model_status":   get_model_status(),
    }
