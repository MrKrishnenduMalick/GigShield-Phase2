"""
GigShield — Business Logic
JWT · OTP · Premium Engine · Fraud Detection · Triggers · Weather
"""
import os, time, random, string, hashlib, json
from datetime import datetime, timedelta
from typing import Optional
from services.db import (
    db, row_to_dict, rows_to_list, now_iso,
    ZONE_RISK, CITY_SEASONAL, BASE_PREMIUM, WEEKLY_CAP, MAX_CLAIMS,
    VEHICLE_RISK, PLATFORM_RISK, MOCK_WEATHER, CITY_COORDS
)

try:
    import httpx; _HTTPX = True
except ImportError:
    _HTTPX = False

SECRET_KEY = os.getenv("JWT_SECRET", "gigshield-insurtech-2026-key")
ALGORITHM  = "HS256"
TOKEN_DAYS = 7

# ── JWT ──────────────────────────────────────────────────────
def make_token(data: dict) -> str:
    try:
        from jose import jwt
        payload = {**data, "exp": datetime.utcnow() + timedelta(days=TOKEN_DAYS)}
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    except ImportError:
        raw = f"{data}:{time.time()}:{random.random()}"
        tok = hashlib.sha256(raw.encode()).hexdigest()
        with db() as conn:
            conn.execute("INSERT OR REPLACE INTO sessions(token,worker_id,created_at) VALUES(?,?,?)",
                         (tok, data.get("worker_id"), now_iso()))
        return tok

def read_token(token: str) -> Optional[dict]:
    try:
        from jose import jwt, JWTError
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        with db() as conn:
            row = conn.execute("SELECT worker_id FROM sessions WHERE token=?", (token,)).fetchone()
        return {"worker_id": row["worker_id"]} if row else None

# ── OTP ──────────────────────────────────────────────────────
def generate_otp(phone: str) -> str:
    otp = str(random.randint(100000, 999999))
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO otp_store(phone,otp,expires,attempts,verified) VALUES(?,?,?,0,0)",
                     (phone, otp, time.time() + 300))
    return otp

def verify_otp(phone: str, otp: str) -> bool:
    with db() as conn:
        row = conn.execute("SELECT * FROM otp_store WHERE phone=?", (phone,)).fetchone()
        if not row: return False
        if time.time() > row["expires"]: return False
        attempts = row["attempts"] + 1
        conn.execute("UPDATE otp_store SET attempts=? WHERE phone=?", (attempts, phone))
        if attempts > 5: return False
        if row["otp"] == otp:
            conn.execute("UPDATE otp_store SET verified=1 WHERE phone=?", (phone,))
            return True
    return False

def is_otp_verified(phone: str) -> bool:
    with db() as conn:
        row = conn.execute("SELECT verified FROM otp_store WHERE phone=?", (phone,)).fetchone()
    return bool(row and row["verified"])

async def send_sms(phone: str, otp: str) -> None:
    key = os.getenv("FAST2SMS_KEY", "")
    if key and _HTTPX:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                await c.post("https://www.fast2sms.com/dev/bulkV2",
                    headers={"authorization": key},
                    json={"route":"otp","variables_values":otp,"numbers":phone})
        except Exception: pass
    print(f"\n  ┌──────────────────────────────┐")
    print(f"  │  GigShield OTP               │")
    print(f"  │  Phone : +91-{phone}  │")
    print(f"  │  OTP   : {otp}               │")
    print(f"  └──────────────────────────────┘\n")

# ── RISK SCORE ────────────────────────────────────────────────
def compute_risk_score(zone, city, vehicle, platform, rain=0, temp=30, aqi=80) -> dict:
    s = 0
    s += min(int((ZONE_RISK.get(zone,1.0)-1.0)/0.30*30), 30)
    s += min(int((CITY_SEASONAL.get(city,1.0)-1.0)/0.20*20), 20)
    w = 20 if rain>80 else 12 if rain>40 else 18 if temp>42 else 10 if temp>38 else 15 if aqi>300 else 8 if aqi>200 else 0
    s += min(w, 20)
    s += int(VEHICLE_RISK.get(vehicle,15)*15/25)
    s += int(PLATFORM_RISK.get(platform,15)*10/20)
    s = max(0, min(100, s))
    return {"score":s, "level":"LOW" if s<35 else "MEDIUM" if s<65 else "HIGH"}

# ── DYNAMIC PREMIUM ───────────────────────────────────────────
def calculate_premium(plan, zone, city, weeks_clean=0, rain=0, temp=30, aqi=80) -> dict:
    base = BASE_PREMIUM.get(plan, 30.0)
    zr   = ZONE_RISK.get(zone, 1.0)
    sf   = CITY_SEASONAL.get(city, 1.0)
    if rain>80 or temp>42 or aqi>300: sf = min(sf*1.1, 1.3)
    ly   = min(weeks_clean*0.5, 3.0) if weeks_clean>=8 else 0.0
    dy   = round(base*zr*sf - ly, 2)
    return {"base":base,"zone_risk":zr,"seasonal":round(sf,3),"loyalty":ly,"dynamic":dy,
            "cap":WEEKLY_CAP.get(plan,200.0),"max_claims":MAX_CLAIMS.get(plan,2),
            "formula":f"₹{base} × {zr} × {round(sf,3)} − ₹{ly} = ₹{dy}"}

# ── EARNINGS PREDICTOR ────────────────────────────────────────
def predict_earnings(city, zone) -> float:
    cm = {"Mumbai":1.15,"Bangalore":1.10,"Delhi":1.08,"Chennai":1.05,"Kolkata":1.03,"Hyderabad":1.02}
    return round(3500.0 * cm.get(city,1.0) * (0.9+ZONE_RISK.get(zone,1.0)*0.1), 0)

# ── FRAUD DETECTION ───────────────────────────────────────────
def compute_fraud_score(gps_points, active_minutes, avg_speed, duration) -> dict:
    s, flags = 0, []
    if gps_points<10:          s+=30; flags.append("LOW_GPS_COVERAGE")
    elif duration>0 and gps_points/max(1,duration)<0.3: s+=20; flags.append("SPARSE_GPS")
    ratio = active_minutes/max(1,duration)
    if ratio<0.10:   s+=30; flags.append("NO_ACTIVITY")
    elif ratio<0.20: s+=20; flags.append("LOW_ACTIVITY")
    elif ratio<0.30: s+=10; flags.append("BELOW_AVG")
    if avg_speed>120: s+=25; flags.append("IMPOSSIBLE_SPEED")
    elif avg_speed<0.5 and active_minutes>30: s+=20; flags.append("STATIONARY")
    s = max(0,min(100,s))
    verdict = "AUTO_APPROVED" if s<40 else "MANUAL_REVIEW" if s<70 else "AUTO_REJECTED"
    return {"score":s,"verdict":verdict,"flags":flags}

# ── TRIGGERS ─────────────────────────────────────────────────
def evaluate_triggers(rain, temp, aqi) -> list:
    t = []
    if   rain>150: t.append({"type":"URBAN_FLOOD",   "val":rain,"mult":1.5,"label":"Urban Flooding 🌊","hours":3.0})
    elif rain>80:  t.append({"type":"HEAVY_RAIN",    "val":rain,"mult":1.0,"label":"Heavy Rainfall 🌧️","hours":2.0})
    elif rain>40:  t.append({"type":"MODERATE_RAIN", "val":rain,"mult":0.6,"label":"Moderate Rain 🌦️","hours":1.5})
    if   temp>42:  t.append({"type":"EXTREME_HEAT",  "val":temp,"mult":1.0,"label":"Extreme Heat 🌡️","hours":2.5})
    if   aqi>300:  t.append({"type":"SEVERE_AQI",    "val":aqi, "mult":1.0,"label":"Severe AQI 😷","hours":2.0})
    return t

# ── CLAIM FORMULA ─────────────────────────────────────────────
def calculate_claim(predicted_weekly, hours_lost, multiplier) -> dict:
    daily_slice = predicted_weekly / 6.0
    raw = round(0.5 * daily_slice * hours_lost * multiplier, 2)
    return {"daily_slice":round(daily_slice,2),"hours_lost":hours_lost,
            "multiplier":multiplier,"raw_amount":raw,
            "formula":f"0.5 × (₹{predicted_weekly:.0f}/6) × {hours_lost}h × {multiplier}× = ₹{raw:.2f}"}

# ── WEATHER ───────────────────────────────────────────────────
async def get_weather(city: str) -> dict:
    owm = os.getenv("OWM_API_KEY","")
    if owm and _HTTPX:
        coords = CITY_COORDS.get(city)
        if coords:
            try:
                async with httpx.AsyncClient(timeout=4.0) as c:
                    lat,lon = coords
                    r = await c.get("https://api.openweathermap.org/data/2.5/weather",
                        params={"lat":lat,"lon":lon,"appid":owm,"units":"metric"})
                    if r.status_code==200:
                        d=r.json(); rain=d.get("rain",{}).get("1h",0)
                        temp=d["main"]["temp"]; hum=d["main"]["humidity"]
                        cond=d["weather"][0]["description"].title()
                        ar = await c.get("https://api.openweathermap.org/data/2.5/air_pollution",
                            params={"lat":lat,"lon":lon,"appid":owm})
                        aqi=80
                        if ar.status_code==200:
                            aqi={1:40,2:90,3:160,4:250,5:380}.get(ar.json()["list"][0]["main"]["aqi"],80)
                        return {"rain_mm":round(rain,1),"temp_c":round(temp,1),"aqi":aqi,
                                "condition":cond,"humidity":hum,"source":"live"}
            except Exception: pass
    base = MOCK_WEATHER.get(city,{"rain_mm":5,"temp_c":30,"aqi":100,"condition":"Clear","humidity":60})
    return {**base,"source":"mock"}
