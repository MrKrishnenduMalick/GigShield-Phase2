"""
GigShield AI — Risk Model
Inputs: weather, shift data, location, history
Output: risk_score 0–100, risk_level, recommendation
"""
import math
from services.db import ZONE_RISK, CITY_SEASONAL


def compute_risk_score(
    zone:            str   = "Unknown",
    city:            str   = "Unknown",
    rain_mm:         float = 0.0,
    temp_c:          float = 30.0,
    aqi:             int   = 80,
    shift_hours:     float = 0.0,
    claims_this_week: int  = 0,
    fraud_history:   float = 0.0,
    latitude:        float = None,
    longitude:       float = None,
) -> dict:
    score = 0.0
    factors = {}

    # ── Zone risk (0–25 pts) ──────────────────────────────────
    zr = ZONE_RISK.get(zone, 1.0)
    zone_pts = min(round((zr - 0.95) / 0.35 * 25, 1), 25)
    score += zone_pts
    factors["zone"] = {"value": zr, "points": zone_pts, "label": zone}

    # ── Weather risk (0–35 pts) ───────────────────────────────
    rain_pts = min(rain_mm / 80 * 20, 20) if rain_mm > 0 else 0
    heat_pts = min(max(temp_c - 38, 0) / 6 * 10, 10)
    aqi_pts  = min(max(aqi - 100, 0) / 200 * 5, 5)
    weather_pts = round(rain_pts + heat_pts + aqi_pts, 1)
    score += weather_pts
    factors["weather"] = {
        "rain_mm": rain_mm, "temp_c": temp_c, "aqi": aqi,
        "points": weather_pts,
        "dominant": "rain" if rain_pts == max(rain_pts, heat_pts, aqi_pts) else
                    "heat" if heat_pts > aqi_pts else "aqi"
    }

    # ── Shift fatigue (0–15 pts) ──────────────────────────────
    fatigue_pts = min(max(shift_hours - 4, 0) / 4 * 15, 15)
    score += fatigue_pts
    factors["fatigue"] = {"shift_hours": shift_hours, "points": round(fatigue_pts, 1)}

    # ── Claims frequency (0–15 pts) ───────────────────────────
    claims_pts = min(claims_this_week * 5, 15)
    score += claims_pts
    factors["claims_freq"] = {"count": claims_this_week, "points": claims_pts}

    # ── Fraud history (0–10 pts) ──────────────────────────────
    fraud_pts = min(fraud_history / 100 * 10, 10)
    score += fraud_pts
    factors["fraud_history"] = {"score": fraud_history, "points": round(fraud_pts, 1)}

    final = round(min(max(score, 0), 100), 1)
    level = "LOW" if final < 30 else "MEDIUM" if final < 60 else "HIGH" if final < 80 else "CRITICAL"

    # Recommendation
    if level == "CRITICAL":
        rec = "⚠️ Stop shift immediately — conditions are dangerous"
    elif level == "HIGH":
        rec = "🔴 Consider ending shift — high disruption risk"
    elif level == "MEDIUM":
        rec = "🟡 Stay alert — moderate risk conditions"
    else:
        rec = "🟢 Safe to work — low risk conditions"

    return {
        "risk_score":  final,
        "risk_level":  level,
        "recommendation": rec,
        "factors":     factors,
        "auto_trigger_threshold": 65,
        "should_auto_trigger":    final >= 65,
    }


def score_from_weather(weather: dict, zone: str = "Unknown", city: str = "Unknown") -> dict:
    """Convenience wrapper — takes a weather dict directly."""
    return compute_risk_score(
        zone     = zone,
        city     = city,
        rain_mm  = weather.get("rain_mm", 0),
        temp_c   = weather.get("temp_c", 30),
        aqi      = weather.get("aqi", 80),
    )
