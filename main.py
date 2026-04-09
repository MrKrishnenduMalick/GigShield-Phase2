"""
GigShield AI Service — FastAPI Backend v4.0  (Phase 3)
═══════════════════════════════════════════════════════
NEW in Phase 3:
  • Start / End Shift  with live GPS ingestion
  • Background auto-trigger  polling Open-Meteo every 5 min
  • APScheduler: Saturday 00:00 reset + Friday 23:59 payout batch
  • Trigger 6 (Short Shift) automatic detection
  • Historical per-event duplicate guard (no repeat same event same day)
  • Mock UPI / Razorpay payout receipt generation
  • Structured logging (Python logging module)
  • Full CORS + error handling
  • 100 % backward-compatible with existing dashboard.html

Run:
    pip install fastapi uvicorn apscheduler httpx
    uvicorn main:app --reload
"""

# ── stdlib ────────────────────────────────────────────────────────
import logging
import math
import random
import asyncio
from datetime import datetime, timezone, date, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager

# ── third-party ───────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    logging.warning("apscheduler not installed — scheduled tasks disabled. pip install apscheduler")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logging.warning("httpx not installed — live weather disabled. pip install httpx")

# ── logging setup ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("gigshield")


# ═══════════════════════════════════════════════════════════════════
#  LIFESPAN  (startup / shutdown — replaces deprecated @app.on_event)
# ═══════════════════════════════════════════════════════════════════

scheduler: Optional[object] = None   # filled at startup

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start APScheduler jobs when the server starts."""
    global scheduler
    if SCHEDULER_AVAILABLE:
        scheduler = AsyncIOScheduler()
        # Every 5 minutes — auto weather poll + claim fire
        scheduler.add_job(auto_weather_trigger, "interval", minutes=5, id="weather_poll")
        # Saturday 00:00 IST → weekly reset + earnings re-prediction
        scheduler.add_job(scheduled_weekly_reset, "cron",
                          day_of_week="sat", hour=0, minute=0, id="weekly_reset")
        # Friday 23:59 IST → payout batch
        scheduler.add_job(scheduled_payout_batch, "cron",
                          day_of_week="fri", hour=23, minute=59, id="payout_batch")
        scheduler.start()
        log.info("✅ APScheduler started — weather poll (5 min) + Saturday reset + Friday payout")
    else:
        log.warning("APScheduler unavailable — cron jobs skipped")

    yield  # app runs here

    if scheduler:
        scheduler.shutdown(wait=False)
        log.info("APScheduler shut down")


# ═══════════════════════════════════════════════════════════════════
#  APP
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="EarnProtect AI Service",
    version="4.0.0",
    description="Parametric micro-insurance backend — Phase 3",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def serve_dashboard():
    return FileResponse("dashboard.html")


# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════

RAIN_THRESHOLD_MM    = 80.0    # mm/hr → HEAVY_RAIN
HEAT_THRESHOLD_C     = 42.0    # °C    → EXTREME_HEAT
AQI_THRESHOLD        = 300     # AQI   → SEVERE_AQI
FLOOD_RAIN_24H_MM    = 150.0   # mm/24h → URBAN_FLOOD
SHORT_SHIFT_HOURS    = 4.0     # Trigger 6 cutoff
MIN_ACTIVE_HOURS     = 1.0     # minimum to attempt a claim
MIN_GPS_POINTS       = 5       # below this → LOW_COVERAGE flag
GLOBAL_WEEKLY_CAP    = 200.0   # fallback if plan not found

SEVERITY = {
    "HEAVY_RAIN":   1.0,
    "EXTREME_HEAT": 1.0,
    "SEVERE_AQI":   1.0,
    "URBAN_FLOOD":  1.5,
    "CURFEW":       1.5,
    "SHORT_SHIFT":  1.0,   # Trigger 6
}

DISRUPTION_LABELS = {
    "HEAVY_RAIN":   "Heavy Rain (>80 mm/hr)",
    "EXTREME_HEAT": "Extreme Heat (>42 °C)",
    "SEVERE_AQI":   "Severe Air Quality (AQI >300)",
    "URBAN_FLOOD":  "Urban Flood Alert",
    "CURFEW":       "Curfew / Section 144",
    "SHORT_SHIFT":  "Short Shift — Weather Forced Exit",
}

PLAN_CAPS        = {"basic": 150.0, "standard": 200.0, "premium": 300.0}
PLAN_MAX_CLAIMS  = {"basic": 1,     "standard": 2,     "premium": 3}
PLAN_PREMIUMS    = {"basic": 20,    "standard": 30,    "premium": 50}


# ═══════════════════════════════════════════════════════════════════
#  IN-MEMORY DATA STORE
# ═══════════════════════════════════════════════════════════════════
#
#  users         → { username: user_dict }
#  shifts        → { username: shift_dict | None }   (one active shift per user)
#  shift_history → list of completed shift_dicts
#  claims        → list of claim_dicts
#  weekly_totals → { username: float }
#  payouts       → list of payout_receipt_dicts
#  weather_cache → last fetched weather dict
# ───────────────────────────────────────────────────────────────────

def generate_mock_earnings_history(base: float = 650.0, days: int = 14) -> List[dict]:
    """Realistic 14-day earnings history; weekends ~15% higher."""
    history = []
    today = date.today()
    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        dow = d.weekday()
        disrupted = random.random() < 0.08
        earnings = (
            0.0 if disrupted
            else base * (1.15 if dow >= 4 else 1.0) * random.uniform(0.85, 1.15)
        )
        history.append({
            "date":        d.isoformat(),
            "earnings":    round(earnings, 2),
            "disrupted":   disrupted,
            "day_of_week": dow,
        })
    return history


def predict_weekly_earnings(history: List[dict]) -> dict:
    """
    Moving-average prediction (PDF §5.2).
    • No data          → random Rs 3,000–4,000
    • < 5 clean days   → weighted moving average (55/20/10/8/7)
    • ≥ 5 clean days   → 7-day rolling mean × 6
    """
    if not history:
        return {"predicted": round(random.uniform(3000, 4000), 2), "method": "default_range"}

    clean = [h for h in history if not h.get("disrupted", False)] or history

    if len(clean) < 5:
        weights  = [0.55, 0.20, 0.10, 0.08, 0.07]
        recent   = [h.get("earnings", 0) for h in clean[:5]]
        while len(recent) < 5:
            recent.append(recent[-1] if recent else 550)
        daily = sum(w * e for w, e in zip(weights, recent))
        if date.today().weekday() >= 4:
            daily *= 1.15
        return {"predicted": round(daily * 6, 2), "method": "weighted_moving_average"}

    avg_daily = sum(h.get("earnings", 0) for h in clean[-7:]) / min(len(clean), 7)
    return {"predicted": round(avg_daily * 6, 2), "method": "moving_average"}

def _make_user(base_daily: float, plan: str) -> dict:
    plan = plan.lower()
    history = generate_mock_earnings_history(base=base_daily)
    pred = predict_weekly_earnings(history)
    return {
        "predicted_income":   pred["predicted"],
        "prediction_method":  pred["method"],
        "plan":               plan,
        "weekly_cap":         PLAN_CAPS.get(plan, GLOBAL_WEEKLY_CAP),
        "max_claims":         PLAN_MAX_CLAIMS.get(plan, 2),
        "active_policy":      True,
        "earnings_history":   history,
        "registered_at":      datetime.now(timezone.utc).isoformat(),
    }

users:         dict = {
    "raju":  _make_user(633.0, "standard"),
    "priya": _make_user(700.0, "premium"),
    "demo":  _make_user(500.0, "basic"),
    "admin": _make_user(1000.0, "premium"),
}
shifts:        dict = {}          # username → active shift dict
shift_history: list = []          # all completed shifts
claims:        list = []          # all claim records
weekly_totals: dict = {}          # username → total approved this week
payouts:       list = []          # payout receipts (Friday batch)
weather_cache: dict = {}          # last fetched weather per city


class GpsPoint(BaseModel):
    lat:       float
    lng:       float
    speed:     Optional[float] = None    # km/h
    accuracy:  Optional[float] = None    # metres (0 = spoofed)
    timestamp: Optional[str]  = None

class StartShiftRequest(BaseModel):
    username: str

class EndShiftRequest(BaseModel):
    username:   str
    gps_points: Optional[List[GpsPoint]] = None

class AddGpsRequest(BaseModel):
    username:  str
    gps_point: GpsPoint

class TriggerRequest(BaseModel):
    username:     str
    working_hours: float
    rain:         Optional[float] = None
    aqi:          Optional[int]   = None
    flood:        Optional[bool]  = False
    heat:         Optional[float] = None          # NEW: explicit heat field
    gps_points:   Optional[List[GpsPoint]] = None
    movement:     Optional[bool] = None

class PredictRequest(BaseModel):
    user_id:          int
    earnings_history: List[dict]

class RiskScoreRequest(BaseModel):
    city:         str
    zone:         str
    vehicle_type: str
    plan_name:    str

class RegisterUserRequest(BaseModel):
    username:             str
    predicted_income:     Optional[float] = None
    plan:                 str
    base_daily_earnings:  Optional[float] = None

class AdminTriggerRequest(BaseModel):
    type: str

class AdminClaimAction(BaseModel):
    reason: Optional[str] = "Manual action"


# ═══════════════════════════════════════════════════════════════════
#  GPS FRAUD DETECTION ENGINE  (unchanged from Phase 2)
# ═══════════════════════════════════════════════════════════════════

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_fraud_score(gps_points: List[GpsPoint]) -> dict:
    score = 0
    flags = []
    n = len(gps_points)

    # ── Rule 1: Low GPS coverage ──────────────────────────────────
    if n < 10:
        score += 30
        flags.append("LOW_COVERAGE")

    # ── Rule 2: GPS spoofing (accuracy == 0) ──────────────────────
    if n > 0:
        spoofed = [p for p in gps_points if p.accuracy is not None and p.accuracy == 0]
        if len(spoofed) / n > 0.8:
            score += 35
            flags.append("GPS_SPOOFING")

    # ── Rule 3: Impossible speed (speed field) ────────────────────
    speed_violations = [p for p in gps_points if p.speed is not None and p.speed > 120]
    if speed_violations:
        score += min(20 * len(speed_violations), 40)
        flags.append("IMPOSSIBLE_SPEED")

    # ── Rule 4: Impossible displacement between consecutive points ─
    if n >= 2:
        jumps = sum(
            1 for i in range(1, n)
            if haversine_km(gps_points[i-1].lat, gps_points[i-1].lng,
                            gps_points[i].lat,   gps_points[i].lng) > 5.0
        )
        if jumps > 0:
            score += min(20 * jumps, 40)
            if "IMPOSSIBLE_SPEED" not in flags:
                flags.append("IMPOSSIBLE_SPEED")

    # ── Rule 5: Stationary (>85% points at same location) ─────────
    if n >= MIN_GPS_POINTS:
        stationary = sum(
            1 for i in range(1, n)
            if abs(gps_points[i].lat - gps_points[i-1].lat) < 0.00005
            and abs(gps_points[i].lng - gps_points[i-1].lng) < 0.00005
        )
        if stationary / (n - 1) > 0.85:
            score += 25
            flags.append("LOW_ACTIVITY")

    final    = min(score, 100)
    decision = "APPROVE" if final < 40 else "REVIEW" if final < 70 else "REJECT"

    explanations = []
    exp_map = {
        "LOW_COVERAGE":    "Insufficient GPS data points during shift",
        "GPS_SPOOFING":    "GPS coordinates appear artificially generated",
        "IMPOSSIBLE_SPEED":"Movement speed exceeds physically possible limits",
        "LOW_ACTIVITY":    "Worker appears stationary — no genuine movement",
    }
    for flag in flags:
        explanations.append(exp_map.get(flag, flag))
    if not flags:
        explanations.append("All GPS checks passed — genuine activity confirmed")

    return {
        "score":       final,
        "flags":       flags,
        "decision":    decision,
        "explanation": explanations,
        "summary":     f"Fraud Score: {final}/100 — {decision}",
    }


def resolve_fraud(gps_points: Optional[List[GpsPoint]], movement: Optional[bool]) -> dict:
    if gps_points and len(gps_points) >= 1:
        return calculate_fraud_score(gps_points)
    if movement is not None:
        return _fraud_from_movement(movement)
    return {
        "score":       55,
        "flags":       ["LOW_COVERAGE", "NO_MOVEMENT"],
        "decision":    "REVIEW",
        "explanation": ["No GPS data or movement flag provided"],
        "summary":     "Fraud Score: 55/100 — REVIEW",
    }


def _fraud_from_movement(movement: bool) -> dict:
    if movement:
        return {"score": 0, "flags": [], "decision": "APPROVE",
                "explanation": ["Movement confirmed"], "summary": "0/100 — APPROVE"}
    return {"score": 55, "flags": ["LOW_ACTIVITY", "NO_MOVEMENT"], "decision": "REVIEW",
            "explanation": ["No movement detected"], "summary": "55/100 — REVIEW"}


# ═══════════════════════════════════════════════════════════════════
#  PAYOUT FORMULA
# ═══════════════════════════════════════════════════════════════════

def calculate_payout(predicted_weekly: float, overlap_hours: float, disruption_type: str) -> float:
    """
    PDF §4.2:  payout = 0.5 × (E_week / 6) × t_overlap × M
    """
    M = SEVERITY.get(disruption_type, 1.0)
    return round(0.5 * (predicted_weekly / 6) * overlap_hours * M, 2)


# ═══════════════════════════════════════════════════════════════════
#  EVENT DETECTION  (now includes heat as a first-class field)
# ═══════════════════════════════════════════════════════════════════

def detect_event_type(rain=None, aqi=None, flood=False, heat=None) -> Optional[str]:
    if flood:
        return "URBAN_FLOOD"
    if rain is not None and rain >= RAIN_THRESHOLD_MM:
        return "HEAVY_RAIN"
    if heat is not None and heat >= HEAT_THRESHOLD_C:
        return "EXTREME_HEAT"
    if aqi is not None and aqi >= AQI_THRESHOLD:
        return "SEVERE_AQI"
    return None


# ═══════════════════════════════════════════════════════════════════
#  HELPER UTILITIES
# ═══════════════════════════════════════════════════════════════════

def today_str() -> str:
    return date.today().isoformat()


def _upi_ref() -> str:
    return "UPI" + "".join(str(random.randint(0, 9)) for _ in range(12))


def _active_hours_from_shift(shift: dict) -> float:
    """Calculate real elapsed hours from shift start_time to now."""
    try:
        start = datetime.fromisoformat(shift["start_time"])
        now   = datetime.now(timezone.utc)
        # make start tz-aware if naive
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        return round((now - start).total_seconds() / 3600, 2)
    except Exception:
        return shift.get("working_hours", 0.0)


# ═══════════════════════════════════════════════════════════════════
#  CLAIM VALIDATION PIPELINE
# ═══════════════════════════════════════════════════════════════════

def validate_claim(username: str, event_type: str, working_hours: float, fraud: dict, source: str = "manual") -> dict:
    """
    Returns {"valid": bool, "status": str, "message": str}.
    Checks: active policy, min hours, fraud flags, duplicate, weekly cap, max claims.
    Advanced: Weather spoofing guard against manual fake claims.
    """
    user = users.get(username)
    if not user or not user.get("active_policy"):
        return {"valid": False, "status": "rejected",
                "message": "Rejected: No active insurance policy this week"}

    if working_hours < MIN_ACTIVE_HOURS:
        return {"valid": False, "status": "rejected",
                "message": f"Rejected: Need at least {MIN_ACTIVE_HOURS}h of active shift"}

    if fraud["decision"] == "REJECT":
        return {"valid": False, "status": "rejected",
                "message": "Rejected: Fraudulent GPS activity detected"}

    # ── Advanced Fraud Guard: Fake weather claims (Historical validation) ──
    # If the claim is generated "manually" (i.e. spoofed/forced outside AI trigger)
    # we simulate checking the global caching or historical database.
    if source == "manual" and event_type in ["HEAVY_RAIN", "EXTREME_HEAT", "URBAN_FLOOD", "SEVERE_AQI"]:
        # MOCK validation logic: Since it wasn't triggered by internal AI (`source=="auto"` or `admin`), 
        # it rejects manual fake weather inputs as a fraud deterrent.
        return {"valid": False, "status": "rejected", 
                "message": "Rejected [Fraud Dept]: Weather Spoofing. Historical DB shows no disruption at this time."}

    # ── Historical duplicate guard: same event same day ───────────
    today = today_str()
    if any(
        c["username"] == username
        and c["event_type"] == event_type
        and c.get("claim_date") == today
        and c["status"] not in ("rejected",)
        for c in claims
    ):
        return {"valid": False, "status": "duplicate",
                "message": f"Rejected: {DISRUPTION_LABELS.get(event_type, event_type)} already claimed today"}

    # ── Weekly cap check ─────────────────────────────────────────
    accumulated = weekly_totals.get(username, 0.0)
    cap = user.get("weekly_cap", GLOBAL_WEEKLY_CAP)
    if accumulated >= cap:
        return {"valid": False, "status": "rejected",
                "message": f"Rejected: Weekly cap of ₹{cap:.0f} already reached"}

    # ── Max claims per week ────────────────────────────────────────
    week_count = sum(
        1 for c in claims
        if c["username"] == username
        and c.get("claim_date", "")[:7] == today[:7]   # same week (YYYY-MM)
        and c["status"] == "approved"
    )
    max_claims = user.get("max_claims", 2)
    if week_count >= max_claims:
        return {"valid": False, "status": "rejected",
                "message": f"Rejected: Max {max_claims} claims/week for your plan"}

    if fraud["decision"] == "REVIEW":
        return {"valid": True, "status": "review",
                "message": "Claim under review — verified before Friday payout"}

    return {"valid": True, "status": "approved", "message": ""}


# ═══════════════════════════════════════════════════════════════════
#  CORE CLAIM BUILDER  (shared by /trigger and auto-trigger)
# ═══════════════════════════════════════════════════════════════════

def _build_and_save_claim(
    username:     str,
    event_type:   str,
    working_hours: float,
    fraud:        dict,
    source:       str = "manual",   # "manual" | "auto" | "admin"
) -> dict:
    """
    Validates, calculates payout, saves claim record, updates weekly_totals.
    Returns the claim record dict.
    """
    validation = validate_claim(username, event_type, working_hours, fraud, source)

    user           = users.get(username, {})
    predicted      = user.get("predicted_income", 3000.0)
    weekly_cap     = user.get("weekly_cap", GLOBAL_WEEKLY_CAP)
    accumulated    = weekly_totals.get(username, 0.0)
    timestamp      = datetime.now(timezone.utc).isoformat()

    # Dynamic overlap: 60% of working_hours, clipped to [0.5, 4.0]
    overlap_hours  = round(max(0.5, min(working_hours * 0.6, 4.0)), 1)
    payout_raw     = calculate_payout(predicted, overlap_hours, event_type)
    payout_capped  = round(min(payout_raw, weekly_cap - accumulated), 2) if validation["valid"] else 0.0

    record = {
        "id":                len(claims) + 1,
        "username":          username,
        "event_type":        event_type,
        "event_label":       DISRUPTION_LABELS.get(event_type, event_type),
        "working_hours":     working_hours,
        "overlap_hours":     overlap_hours,
        "raw_payout":        payout_raw,
        "payout_amount":     payout_capped,
        "fraud_score":       fraud["score"],
        "fraud_flags":       fraud["flags"],
        "fraud_decision":    fraud["decision"],
        "fraud_explanation": fraud["explanation"],
        "status":            validation["status"] if not validation["valid"] else validation["status"],
        "message":           validation["message"] if not validation["valid"] else
                             ("Claim under review — verified before Friday payout"
                              if validation["status"] == "review"
                              else "Claim approved. Paid Friday 23:59."),
        "claim_date":        today_str(),
        "timestamp":         timestamp,
        "source":            source,
        "weekly_total":      round(accumulated + payout_capped, 2),
        "weekly_cap":        weekly_cap,
    }

    claims.append(record)

    if record["status"] == "approved":
        weekly_totals[username] = accumulated + payout_capped
        log.info(
            "CLAIM APPROVED | user=%s event=%s payout=₹%.2f fraud=%d",
            username, event_type, payout_capped, fraud["score"]
        )
    elif record["status"] == "review":
        log.info("CLAIM REVIEW   | user=%s event=%s fraud=%d", username, event_type, fraud["score"])
    else:
        log.info("CLAIM REJECTED | user=%s event=%s reason=%s", username, event_type, validation["message"])

    return record


# ═══════════════════════════════════════════════════════════════════
#  LIVE WEATHER  (Open-Meteo — no API key needed)
# ═══════════════════════════════════════════════════════════════════

# Default coordinates per city (used by auto-trigger)
CITY_COORDS = {
    "mumbai":    (19.076, 72.877),
    "kolkata":   (22.572, 88.363),
    "delhi":     (28.613, 77.209),
    "chennai":   (13.082, 80.270),
    "bangalore": (12.971, 77.594),
    "hyderabad": (17.385, 78.486),
    "noida":     (28.535, 77.391),
}


async def fetch_open_meteo(lat: float, lng: float) -> dict:
    """
    Call Open-Meteo current-weather API (free, no key).
    Returns dict with keys: rain_mm, temp_c, aqi (mocked — Open-Meteo AQI needs separate call).
    Falls back to cached/mock data on any error.
    """
    if not HTTPX_AVAILABLE:
        return _mock_weather()

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lng}"
        "&current=precipitation,temperature_2m,weather_code"
        "&forecast_days=1"
    )
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json().get("current", {})
            return {
                "rain_mm":  round(data.get("precipitation", 0.0), 2),
                "temp_c":   round(data.get("temperature_2m", 30.0), 1),
                "aqi":      0,   # Open-Meteo free tier has no AQI; extend with IQAir if needed
                "source":   "open-meteo",
                "fetched":  datetime.now(timezone.utc).isoformat(),
            }
    except Exception as exc:
        log.warning("Open-Meteo fetch failed (%s) — using mock weather", exc)
        return _mock_weather()


def _mock_weather() -> dict:
    """Randomised but realistic mock weather for demo / offline use."""
    return {
        "rain_mm": round(random.uniform(0, 20), 2),
        "temp_c":  round(random.uniform(28, 38), 1),
        "aqi":     random.randint(50, 180),
        "source":  "mock",
        "fetched": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
#  BACKGROUND: AUTO WEATHER TRIGGER  (every 5 min via APScheduler)
# ═══════════════════════════════════════════════════════════════════

async def auto_weather_trigger():
    """
    Phase 3 — background job:
    1. Fetch live weather for each city with active shifts
    2. Detect parametric events
    3. Auto-fire claims for qualifying active shifts (zero-touch)
    4. Trigger 6: if shift active < SHORT_SHIFT_HOURS + any weather event → SHORT_SHIFT claim
    """
    if not shifts:
        return  # nobody on shift

    log.info("AUTO-TRIGGER: scanning %d active shift(s)", len(shifts))

    for username, shift in list(shifts.items()):
        if not shift:
            continue

        user = users.get(username)
        if not user or not user.get("active_policy"):
            continue

        # Determine city (default Mumbai)
        city = (user.get("city") or "mumbai").lower()
        coords = CITY_COORDS.get(city, CITY_COORDS["mumbai"])

        weather = await fetch_open_meteo(*coords)
        weather_cache[city] = weather

        rain  = weather["rain_mm"]
        temp  = weather["temp_c"]
        aqi   = weather["aqi"]
        flood = rain > FLOOD_RAIN_24H_MM  # simplified; real impl would use 24h accumulation

        event_type = detect_event_type(rain=rain, aqi=aqi, flood=flood, heat=temp)

        working_hours = _active_hours_from_shift(shift)

        # ── Trigger 6: Short Shift ────────────────────────────────
        # If shift is short AND any weather disruption present, fire SHORT_SHIFT
        short_shift = working_hours < SHORT_SHIFT_HOURS and (
            rain > 40 or temp > 38 or aqi > 200
        )

        if not event_type and not short_shift:
            log.debug("AUTO-TRIGGER: no event for %s (rain=%.1f temp=%.1f aqi=%d)",
                      username, rain, temp, aqi)
            continue

        final_event = event_type if event_type else "SHORT_SHIFT"
        gps_pts = [GpsPoint(**p) for p in shift.get("gps_points", [])]
        fraud   = resolve_fraud(gps_pts if gps_pts else None, None)

        claim = _build_and_save_claim(
            username=username,
            event_type=final_event,
            working_hours=working_hours,
            fraud=fraud,
            source="auto",
        )
        log.info(
            "AUTO-TRIGGER fired | user=%s event=%s hours=%.1f status=%s payout=₹%.2f",
            username, final_event, working_hours, claim["status"], claim["payout_amount"]
        )


# ═══════════════════════════════════════════════════════════════════
#  SCHEDULED: SATURDAY 00:00 — WEEKLY RESET
# ═══════════════════════════════════════════════════════════════════

async def scheduled_weekly_reset():
    """
    PDF §11.1 step 1 — Saturday 00:00:
    • Reset weekly_totals accumulator
    • Re-run earnings prediction for all users
    • Mark old claims as 'week_closed' (preserve for audit)
    """
    log.info("═══ SATURDAY RESET: New insurance week starting ═══")

    weekly_totals.clear()

    for username, user in users.items():
        history = generate_mock_earnings_history(base=random.uniform(550, 750))
        pred    = predict_weekly_earnings(history)
        user["predicted_income"]  = pred["predicted"]
        user["prediction_method"] = pred["method"]
        user["earnings_history"]  = history
        user["active_policy"]     = True
        log.info("  Earnings re-predicted | user=%s predicted=₹%.2f method=%s",
                 username, pred["predicted"], pred["method"])

    # Mark this-week claims as archived
    week_tag = f"week_{(date.today() - timedelta(days=1)).strftime('%Y-%W')}"
    for c in claims:
        if c.get("week_tag") is None:
            c["week_tag"] = week_tag

    log.info("═══ SATURDAY RESET COMPLETE ═══")


# ═══════════════════════════════════════════════════════════════════
#  SCHEDULED: FRIDAY 23:59 — PAYOUT BATCH
# ═══════════════════════════════════════════════════════════════════

async def scheduled_payout_batch():
    """
    PDF §11.1 step 3-9 — Friday 23:59:
    • Sum all approved claims per worker
    • Apply weekly cap
    • Mock UPI/Razorpay transfer → generate receipt
    • Mark claims as 'paid'
    • Push WebSocket-style event into payouts list (frontend polls /payouts)
    """
    log.info("═══ FRIDAY PAYOUT BATCH STARTING ═══")

    # Group approved claims by username
    user_claims: dict = {}
    for c in claims:
        if c["status"] == "approved":
            user_claims.setdefault(c["username"], []).append(c)

    batch_total = 0.0
    for username, uclaims in user_claims.items():
        user    = users.get(username, {})
        cap     = user.get("weekly_cap", GLOBAL_WEEKLY_CAP)
        total   = min(sum(c["payout_amount"] for c in uclaims), cap)
        ref     = _upi_ref()
        receipt = {
            "username":     username,
            "week_ending":  today_str(),
            "claims_count": len(uclaims),
            "total_paid":   round(total, 2),
            "weekly_cap":   cap,
            "upi_ref":      ref,
            "razorpay_id":  f"pay_{ref[3:]}",
            "status":       "SUCCESS",
            "paid_at":      datetime.now(timezone.utc).isoformat(),
            "message":      f"₹{total:.0f} credited via UPI | Ref: {ref}",
        }
        payouts.append(receipt)

        for c in uclaims:
            c["status"]   = "paid"
            c["paid_at"]  = receipt["paid_at"]
            c["upi_ref"]  = ref

        batch_total += total
        log.info("  PAID | user=%s amount=₹%.2f claims=%d ref=%s",
                 username, total, len(uclaims), ref)

    log.info("═══ FRIDAY PAYOUT COMPLETE | total_disbursed=₹%.2f ═══", batch_total)


# ═══════════════════════════════════════════════════════════════════
#  SHIFT ENDPOINTS  (NEW in Phase 3)
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/shift/start")
def start_shift(req: StartShiftRequest):
    """
    Begin a new shift for a worker.
    Stores start_time; GPS points collected incrementally via /api/shift/gps.
    """
    username = req.username.lower().strip()

    if username not in users:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    if not users[username].get("active_policy"):
        raise HTTPException(status_code=403, detail="No active insurance policy this week")
    if shifts.get(username):
        raise HTTPException(status_code=409, detail="Shift already active for this user")

    shifts[username] = {
        "username":    username,
        "start_time":  datetime.now(timezone.utc).isoformat(),
        "gps_points":  [],
        "working_hours": 0.0,
    }
    log.info("SHIFT START | user=%s", username)
    return {
        "success":    True,
        "message":    f"Shift started for {username}",
        "start_time": shifts[username]["start_time"],
    }


@app.post("/api/shift/gps")
def add_gps_point(req: AddGpsRequest):
    """
    Append a single GPS point to the active shift (called every ~10 s by frontend).
    """
    username = req.username.lower().strip()
    if not shifts.get(username):
        raise HTTPException(status_code=404, detail="No active shift for this user")

    point_dict = {
        "lat":       req.gps_point.lat,
        "lng":       req.gps_point.lng,
        "speed":     req.gps_point.speed,
        "accuracy":  req.gps_point.accuracy,
        "timestamp": req.gps_point.timestamp or datetime.now(timezone.utc).isoformat(),
    }
    shifts[username]["gps_points"].append(point_dict)
    return {
        "success":    True,
        "points_so_far": len(shifts[username]["gps_points"]),
    }


@app.post("/api/shift/end")
def end_shift(req: EndShiftRequest, background_tasks: BackgroundTasks):
    """
    End an active shift.
    • Calculates real active_hours from timestamps
    • Merges any extra GPS points sent in the request
    • Runs fraud analysis
    • Returns shift summary
    • Triggers auto-claim evaluation in background (Trigger 6 + live weather check)
    """
    username = req.username.lower().strip()
    shift    = shifts.get(username)
    if not shift:
        raise HTTPException(status_code=404, detail="No active shift for this user")

    end_time = datetime.now(timezone.utc).isoformat()

    # Merge any GPS points from request
    if req.gps_points:
        for p in req.gps_points:
            shift["gps_points"].append({
                "lat": p.lat, "lng": p.lng,
                "speed": p.speed, "accuracy": p.accuracy,
                "timestamp": p.timestamp or end_time,
            })

    working_hours = _active_hours_from_shift(shift)
    gps_pts       = [GpsPoint(**p) for p in shift["gps_points"]]
    fraud         = resolve_fraud(gps_pts if gps_pts else None, None)

    summary = {
        "username":      username,
        "start_time":    shift["start_time"],
        "end_time":      end_time,
        "working_hours": working_hours,
        "gps_count":     len(gps_pts),
        "fraud_score":   fraud["score"],
        "fraud_decision":fraud["decision"],
        "fraud_flags":   fraud["flags"],
    }
    shift_history.append({**summary, "gps_points": shift["gps_points"]})
    del shifts[username]

    # Fire claim evaluation in background (non-blocking)
    background_tasks.add_task(_post_shift_claim_check, username, working_hours, fraud)

    log.info("SHIFT END | user=%s hours=%.2f fraud=%d", username, working_hours, fraud["score"])
    return {"success": True, "summary": summary}


async def _post_shift_claim_check(username: str, working_hours: float, fraud: dict):
    """
    Background task called after shift ends.
    Checks live weather; if event active fires claim automatically.
    Also handles Trigger 6 (Short Shift).
    """
    user   = users.get(username)
    city   = (user.get("city") or "mumbai").lower() if user else "mumbai"
    coords = CITY_COORDS.get(city, CITY_COORDS["mumbai"])

    weather   = await fetch_open_meteo(*coords)
    rain      = weather["rain_mm"]
    temp      = weather["temp_c"]
    aqi       = weather["aqi"]
    flood     = rain > FLOOD_RAIN_24H_MM
    event     = detect_event_type(rain=rain, aqi=aqi, flood=flood, heat=temp)
    short     = working_hours < SHORT_SHIFT_HOURS and (rain > 40 or temp > 38 or aqi > 200)

    final_event = event if event else ("SHORT_SHIFT" if short else None)
    if not final_event:
        return

    _build_and_save_claim(
        username=username,
        event_type=final_event,
        working_hours=working_hours,
        fraud=fraud,
        source="auto_shift_end",
    )


@app.get("/api/shift/active/{username}")
def get_active_shift(username: str):
    """Check whether a worker currently has an active shift."""
    username = username.lower().strip()
    shift    = shifts.get(username)
    if not shift:
        return {"active": False}
    hours = _active_hours_from_shift(shift)
    return {
        "active":        True,
        "start_time":    shift["start_time"],
        "working_hours": hours,
        "gps_count":     len(shift["gps_points"]),
    }


@app.get("/api/shift/history/{username}")
def get_shift_history(username: str):
    """Return last 10 completed shifts for a worker."""
    username = username.lower().strip()
    history  = [s for s in shift_history if s["username"] == username]
    return {"success": True, "data": history[-10:]}


# ═══════════════════════════════════════════════════════════════════
#  TRIGGER ENDPOINT  (backward-compatible + now includes heat field)
# ═══════════════════════════════════════════════════════════════════

@app.post("/trigger")
def trigger_claim(req: TriggerRequest):
    """
    Manual / frontend trigger.  Fully backward-compatible with Phase 2 dashboard.
    Now also handles req.heat for Extreme Heat trigger.
    """
    username   = req.username.lower().strip()
    event_type = detect_event_type(
        rain=req.rain, aqi=req.aqi, flood=req.flood or False, heat=req.heat
    )
    if event_type is None:
        raise HTTPException(
            status_code=400,
            detail="No parametric threshold met. Provide rain≥80mm, heat≥42°C, AQI≥300, or flood=true."
        )

    fraud  = resolve_fraud(req.gps_points, req.movement)
    record = _build_and_save_claim(
        username=username,
        event_type=event_type,
        working_hours=req.working_hours,
        fraud=fraud,
        source="manual",
    )
    return {"success": True, "claim": record}


# ═══════════════════════════════════════════════════════════════════
#  USER ENDPOINTS  (unchanged from Phase 2)
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/users/register")
def register_user(req: RegisterUserRequest):
    plan = req.plan.lower()
    if plan not in PLAN_CAPS:
        raise HTTPException(status_code=400, detail="Invalid plan. Choose basic | standard | premium")

    base_daily = req.base_daily_earnings or 633.0
    history    = generate_mock_earnings_history(base=base_daily)
    pred       = predict_weekly_earnings(history)
    predicted  = req.predicted_income if req.predicted_income else pred["predicted"]

    users[req.username.lower()] = {
        "predicted_income":  predicted,
        "prediction_method": pred["method"],
        "plan":              plan,
        "weekly_cap":        PLAN_CAPS[plan],
        "max_claims":        PLAN_MAX_CLAIMS[plan],
        "active_policy":     True,
        "earnings_history":  history,
        "registered_at":     datetime.now(timezone.utc).isoformat(),
    }
    log.info("USER REGISTERED | user=%s plan=%s predicted=₹%.2f", req.username, plan, predicted)
    return {
        "success":           True,
        "message":           f"User {req.username} registered on {plan} plan.",
        "predicted_income":  predicted,
        "prediction_method": pred["method"],
        "weekly_cap":        PLAN_CAPS[plan],
        "weekly_premium":    PLAN_PREMIUMS[plan],
        "max_claims":        PLAN_MAX_CLAIMS[plan],
    }


@app.get("/api/users/{username}")
def get_user(username: str):
    user = users.get(username.lower())
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "data": {k: v for k, v in user.items() if k != "earnings_history"}}


@app.get("/api/claims/{username}")
def get_claims_by_user(username: str):
    uname      = username.lower()
    user_claims = [c for c in claims if c["username"] == uname]
    return {
        "success":      True,
        "username":     uname,
        "data":         user_claims,
        "weekly_total": round(weekly_totals.get(uname, 0.0), 2),
        "count":        len(user_claims),
    }


@app.get("/api/claims")
def get_all_claims():
    return {"success": True, "data": claims, "total": len(claims)}


@app.post("/api/analyze-gps")
def analyze_gps(points: List[GpsPoint]):
    return {"success": True, "data": calculate_fraud_score(points)}


@app.post("/api/predict-earnings")
def predict_earnings_endpoint(req: PredictRequest):
    return {"success": True, "data": predict_weekly_earnings(req.earnings_history)}


@app.post("/api/risk-score")
def risk_score(req: RiskScoreRequest):
    zone_risk = {
        "bandra": 0.85, "andheri": 0.75, "salt_lake": 0.70,
        "t_nagar": 0.60, "koramangala": 0.45, "connaught_place": 0.35,
        "sector_18": 0.40, "jubilee_hills": 0.30,
    }.get(req.zone.lower().replace(" ", "_"), 0.50)

    vehicle_risk = {"bicycle": 0.80, "motorcycle": 0.60, "ev": 0.55}.get(
        req.vehicle_type.lower(), 0.60)

    base    = PLAN_PREMIUMS.get(req.plan_name.lower(), 30)
    dynamic = round(base * (1 + zone_risk * 0.3) * (1 + vehicle_risk * 0.15), 2)

    return {"success": True, "data": {
        "base_premium":    base,
        "dynamic_premium": dynamic,
        "zone_risk":       zone_risk,
        "vehicle_risk":    vehicle_risk,
    }}


# ═══════════════════════════════════════════════════════════════════
#  PAYOUT HISTORY ENDPOINT  (NEW in Phase 3)
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/payouts/{username}")
def get_payouts(username: str):
    """Returns all UPI payout receipts for a worker."""
    uname   = username.lower()
    receipts = [p for p in payouts if p["username"] == uname]
    return {"success": True, "data": receipts, "total": len(receipts)}


@app.get("/api/payouts")
def get_all_payouts():
    return {"success": True, "data": payouts, "total": len(payouts)}


# ═══════════════════════════════════════════════════════════════════
#  WEATHER ENDPOINTS  (NEW in Phase 3)
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/weather/{city}")
async def get_weather(city: str):
    """Fetch live weather for a city (Open-Meteo) and detect active triggers."""
    city_key = city.lower()
    coords   = CITY_COORDS.get(city_key)
    if not coords:
        raise HTTPException(status_code=404, detail=f"City '{city}' not in covered zones")

    weather    = await fetch_open_meteo(*coords)
    event_type = detect_event_type(
        rain=weather["rain_mm"], aqi=weather["aqi"],
        flood=weather["rain_mm"] > FLOOD_RAIN_24H_MM, heat=weather["temp_c"]
    )
    return {
        "success":    True,
        "city":       city,
        "weather":    weather,
        "trigger":    event_type,
        "trigger_label": DISRUPTION_LABELS.get(event_type) if event_type else None,
        "threshold":  {
            "rain_mm":  RAIN_THRESHOLD_MM,
            "aqi":      AQI_THRESHOLD,
            "temp_c":   HEAT_THRESHOLD_C,
        },
    }


@app.get("/api/weather/cache")
def get_weather_cache():
    """Return the last fetched weather for all active cities."""
    return {"success": True, "data": weather_cache}


# ═══════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS  (enhanced in Phase 3)
# ═══════════════════════════════════════════════════════════════════

@app.get("/admin/stats")
def admin_stats():
    approved = [c for c in claims if c["status"] == "approved"]
    paid     = [c for c in claims if c["status"] == "paid"]
    total_approved = round(sum(c["payout_amount"] for c in approved + paid), 2)
    # Loss ratio calculation
    total_premiums = sum(PLAN_PREMIUMS.get(u.get("plan", "basic"), 20) for u in users.values())
    loss_ratio = round(total_approved / max(1, total_premiums), 2)

    predictive_analytics = {
        "likely_claims_next_week": max(1, int(len(users) * 0.2)),
        "forecast_disruptions": "Heavy Rain (Mumbai)",
        "forecast_loss_ratio": round(random.uniform(0.5, 0.9), 2)
    }

    return {
        "totalUsers":       len(users),
        "activeShifts":     len(shifts),
        "totalClaims":      len(claims),
        "approvedClaims":   len(approved),
        "pendingReview":    len([c for c in claims if c["status"] == "review"]),
        "rejectedClaims":   len([c for c in claims if c["status"] == "rejected"]),
        "paidClaims":       len(paid),
        "totalApproved":    total_approved,
        "totalDisbursed":   round(sum(p["total_paid"] for p in payouts), 2),
        "weeklyTotals":     weekly_totals,
        "lossRatio":        loss_ratio,
        "predictiveAnalytics": predictive_analytics,
        "schedulerRunning": SCHEDULER_AVAILABLE and scheduler is not None,
    }


@app.get("/admin/users")
def admin_users():
    return [
        {
            "id":              i + 1,
            "phone":           uname,
            "name":            uname.title(),
            "city":            "Mumbai",
            "vehicleType":     "Motorcycle",
            "kycDone":         True,
            "plan":            u.get("plan"),
            "predicted_income":u.get("predicted_income"),
            "weekly_cap":      u.get("weekly_cap"),
            "active_shift":    uname in shifts,
        }
        for i, (uname, u) in enumerate(users.items())
    ]


@app.get("/admin/shifts")
def admin_shifts():
    active = [
        {
            "username":    uname,
            "start_time":  s["start_time"],
            "working_hours": _active_hours_from_shift(s),
            "gps_count":   len(s["gps_points"]),
            "active":      True,
        }
        for uname, s in shifts.items()
    ]
    history_out = [
        {**s, "active": False, "gps_points": None}
        for s in shift_history[-20:]
    ]
    return {"active": active, "history": history_out}


@app.get("/admin/claims")
def admin_claims():
    return [
        {
            "id":             c.get("id", i + 1),
            "userId":         c["username"],
            "disruptionType": c["event_type"],
            "eventLabel":     c.get("event_label", c["event_type"]),
            "payoutAmount":   c["payout_amount"],
            "fraudScore":     c["fraud_score"],
            "fraudDecision":  c["fraud_decision"],
            "status":         c["status"].upper(),
            "source":         c.get("source", "manual"),
            "createdAt":      c["timestamp"],
            "paidAt":         c.get("paid_at"),
            "upiRef":         c.get("upi_ref"),
        }
        for i, c in enumerate(claims)
    ]


@app.post("/admin/claims/{claim_id}/approve")
def admin_approve_claim(claim_id: int):
    idx = next((i for i, c in enumerate(claims) if c.get("id") == claim_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    claims[idx]["status"] = "approved"
    username = claims[idx]["username"]
    weekly_totals[username] = weekly_totals.get(username, 0.0) + claims[idx]["payout_amount"]
    log.info("ADMIN APPROVE | claim_id=%d user=%s", claim_id, username)
    return {"success": True, "message": "Claim approved"}


@app.post("/admin/claims/{claim_id}/reject")
def admin_reject_claim(claim_id: int, body: AdminClaimAction):
    idx = next((i for i, c in enumerate(claims) if c.get("id") == claim_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    claims[idx]["status"]  = "rejected"
    claims[idx]["message"] = f"Rejected by admin: {body.reason}"
    log.info("ADMIN REJECT  | claim_id=%d reason=%s", claim_id, body.reason)
    return {"success": True, "message": "Claim rejected"}


@app.post("/admin/simulate-trigger")
def admin_simulate_trigger(req: AdminTriggerRequest):
    """Simulate a disruption for ALL active-policy users (demo/testing)."""
    triggered = 0
    for username, user in users.items():
        if not user.get("active_policy"):
            continue
        fraud = {"score": 0, "flags": [], "decision": "APPROVE",
                 "explanation": ["Admin simulation"], "summary": "APPROVE"}
        record = _build_and_save_claim(
            username=username, event_type=req.type,
            working_hours=4.0, fraud=fraud, source="admin_simulate"
        )
        if record["status"] == "approved":
            triggered += 1

    return {"success": True, "message": f"Trigger fired. {triggered} claim(s) approved."}


@app.post("/admin/payout-now")
async def admin_payout_now():
    """Manually run the Friday payout batch (for demo/testing)."""
    await scheduled_payout_batch()
    return {"success": True, "message": "Payout batch executed.", "receipts": payouts[-len(users):]}


@app.post("/admin/weekly-reset-now")
async def admin_weekly_reset_now():
    """Manually run Saturday reset (for demo/testing)."""
    await scheduled_weekly_reset()
    return {"success": True, "message": "Weekly reset executed."}


# ═══════════════════════════════════════════════════════════════════
#  BACKWARD-COMPAT ENDPOINTS  (kept from Phase 2)
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/weekly-reset")
async def weekly_reset():
    await scheduled_weekly_reset()
    return {"success": True, "message": "Weekly totals and claims reset for new insurance week."}


# ═══════════════════════════════════════════════════════════════════
#  HEALTH
# ═══════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {
        "status":            "ok",
        "service":           "EarnProtect AI",
        "version":           "4.0.0",
        "phase":             3,
        "registered_users":  len(users),
        "active_shifts":     len(shifts),
        "total_claims":      len(claims),
        "total_payouts":     len(payouts),
        "scheduler_running": SCHEDULER_AVAILABLE and scheduler is not None,
        "httpx_available":   HTTPX_AVAILABLE,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }
