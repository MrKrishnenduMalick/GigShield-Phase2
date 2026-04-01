"""
GigShield ML — Random Forest Risk Model
Trains on synthetic historical disruption data.
Outputs: risk_score (0-100), premium_multiplier, next_week_prediction
"""

import os, json, math, random
from datetime import datetime

# Try importing sklearn — graceful fallback to rule-based if not installed
try:
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

MODEL_PATH = os.path.join(os.path.dirname(__file__), "trained_model.json")

# ── SYNTHETIC TRAINING DATA ──────────────────────────────────
def _generate_training_data(n=2000):
    """Generate realistic historical disruption data for training."""
    random.seed(42)
    X, y = [], []
    
    cities  = ["Mumbai","Delhi","Kolkata","Chennai","Bangalore","Hyderabad","Noida"]
    city_risk = {"Mumbai":0.8,"Kolkata":0.7,"Chennai":0.6,"Delhi":0.5,"Bangalore":0.4,"Hyderabad":0.35,"Noida":0.45}
    
    for _ in range(n):
        rain_mm  = random.choices([0,0,0,random.uniform(0,40),random.uniform(40,80),random.uniform(80,200)],
                                   weights=[30,20,15,15,12,8])[0]
        temp_c   = random.gauss(32, 8)
        aqi      = random.choices([random.randint(30,100),random.randint(100,200),random.randint(200,400)],
                                   weights=[50,30,20])[0]
        city     = random.choice(cities)
        hour     = random.randint(0, 23)
        is_weekend= random.choice([0,1])
        month    = random.randint(1,12)
        is_monsoon= 1 if month in [6,7,8,9] else 0
        shift_h  = random.uniform(2, 12)
        
        base_risk = city_risk[city]
        rain_risk  = min(rain_mm/80, 1.0) * 0.4
        heat_risk  = max(0, (temp_c-38)/8) * 0.2
        aqi_risk   = max(0, (aqi-150)/250) * 0.15
        hour_risk  = 0.1 if hour in [7,8,9,17,18,19,20] else 0.0
        monsoon_r  = 0.15 if is_monsoon else 0.0
        
        prob = min(base_risk + rain_risk + heat_risk + aqi_risk + hour_risk + monsoon_r, 1.0)
        disrupted = 1 if random.random() < prob else 0
        
        X.append([rain_mm, temp_c, aqi, base_risk, hour, is_weekend, is_monsoon, shift_h, month])
        y.append(disrupted)
    
    return X, y


def _generate_earnings_data(n=1500):
    """Training data for earnings prediction model."""
    random.seed(123)
    X, y = [], []
    
    for _ in range(n):
        zone_risk   = random.uniform(1.0, 1.35)
        city_factor = random.uniform(1.0, 1.2)
        rain_mm     = random.uniform(0, 150)
        temp_c      = random.gauss(32, 7)
        aqi         = random.uniform(30, 400)
        is_weekend  = random.choice([0,1])
        is_monsoon  = random.choice([0,1])
        shift_hours = random.uniform(3, 12)
        weeks_clean = random.randint(0, 20)
        
        base_earn  = 3500 * city_factor * (0.9 + zone_risk * 0.1)
        rain_pen   = min(rain_mm / 80, 1.0) * 0.3
        heat_pen   = max(0, (temp_c - 40)/10) * 0.15
        aqi_pen    = max(0, (aqi - 200)/200) * 0.1
        wknd_bonus = 0.12 if is_weekend else 0
        hours_mult = min(shift_hours / 8, 1.2)
        
        earnings = base_earn * (1 - rain_pen - heat_pen - aqi_pen + wknd_bonus) * hours_mult
        earnings += random.gauss(0, 200)
        earnings  = max(800, min(8000, earnings))
        
        X.append([zone_risk, city_factor, rain_mm, temp_c, aqi, is_weekend, is_monsoon, shift_hours, weeks_clean])
        y.append(round(earnings, 2))
    
    return X, y


# ── MODEL TRAINING ────────────────────────────────────────────
_risk_model     = None
_earnings_model = None
_is_trained     = False


def train_models():
    """Train both models. Called once at startup."""
    global _risk_model, _earnings_model, _is_trained
    
    if not ML_AVAILABLE:
        _is_trained = False
        print("[GigShield ML] scikit-learn not installed → using rule-based fallback")
        return
    
    try:
        # Risk classification model
        X_r, y_r = _generate_training_data(2000)
        _risk_model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf",    RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1))
        ])
        _risk_model.fit(X_r, y_r)
        
        # Earnings regression model
        X_e, y_e = _generate_earnings_data(1500)
        _earnings_model = Pipeline([
            ("scaler",    StandardScaler()),
            ("regressor", GradientBoostingRegressor(n_estimators=100, max_depth=5, random_state=42))
        ])
        _earnings_model.fit(X_e, y_e)
        
        _is_trained = True
        print(f"[GigShield ML] ✅ Models trained (RF + GBR) on synthetic data")
    except Exception as e:
        _is_trained = False
        print(f"[GigShield ML] Training failed: {e} → fallback active")


def predict_disruption_probability(
    rain_mm: float, temp_c: float, aqi: float,
    city: str = "Mumbai", zone: str = "Bandra",
    hour: int = None, is_weekend: int = 0,
    is_monsoon: int = None, shift_hours: float = 4.0,
) -> dict:
    """
    Predict probability of income disruption this shift.
    Returns: probability (0–1), risk_score (0–100), confidence.
    """
    from services.db import ZONE_RISK, CITY_SEASONAL
    
    now = datetime.utcnow()
    if hour is None:      hour      = now.hour
    if is_monsoon is None: is_monsoon = 1 if now.month in [6,7,8,9] else 0
    
    zone_risk_val  = ZONE_RISK.get(zone, 1.0)
    city_base_risk = {"Mumbai":0.8,"Kolkata":0.7,"Chennai":0.6,"Delhi":0.5,
                      "Bangalore":0.4,"Hyderabad":0.35,"Noida":0.45}.get(city, 0.5)
    
    if _is_trained and _risk_model is not None:
        features = [[rain_mm, temp_c, aqi, city_base_risk, hour, is_weekend, is_monsoon, shift_hours, now.month]]
        prob = float(_risk_model.predict_proba(features)[0][1])
        confidence = "HIGH"
        method = "RandomForest"
    else:
        # Rule-based fallback
        prob  = min(
            city_base_risk
            + min(rain_mm/80, 1.0)*0.4
            + max(0, (temp_c-38)/8)*0.2
            + max(0, (aqi-150)/250)*0.15
            + (0.15 if is_monsoon else 0), 1.0
        )
        confidence = "MEDIUM"
        method = "RuleBased"
    
    risk_score = round(prob * 100, 1)
    level      = "LOW" if risk_score < 30 else "MEDIUM" if risk_score < 60 else "HIGH" if risk_score < 80 else "CRITICAL"
    
    return {
        "probability":  round(prob, 3),
        "risk_score":   risk_score,
        "risk_level":   level,
        "confidence":   confidence,
        "method":       method,
        "is_monsoon":   bool(is_monsoon),
        "recommendation": _recommendation(level),
        "should_auto_trigger": risk_score >= 65,
    }


def predict_weekly_earnings(
    city: str, zone: str,
    rain_mm: float = 0, temp_c: float = 30, aqi: float = 80,
    is_weekend: int = 0, weeks_clean: int = 0,
    shift_hours: float = 8.0,
) -> dict:
    """Predict weekly earnings using GBR model."""
    from services.db import ZONE_RISK, CITY_SEASONAL
    
    now = datetime.utcnow()
    is_monsoon  = 1 if now.month in [6,7,8,9] else 0
    zone_risk   = ZONE_RISK.get(zone, 1.0)
    city_factor = CITY_SEASONAL.get(city, 1.0)
    
    if _is_trained and _earnings_model is not None:
        feats = [[zone_risk, city_factor, rain_mm, temp_c, aqi, is_weekend, is_monsoon, shift_hours, weeks_clean]]
        pred  = float(_earnings_model.predict(feats)[0])
        method = "GradientBoosting"
    else:
        base  = 3500.0
        pred  = base * city_factor * (0.9 + zone_risk * 0.1)
        pred *= (1 - min(rain_mm/80, 1.0)*0.3)
        pred *= (1 - max(0,(temp_c-40)/10)*0.15)
        pred *= (1.12 if is_weekend else 1.0)
        method = "RuleBased"
    
    pred = max(800, min(9000, round(pred, 0)))
    
    # Next-week prediction with slight variance
    next_week_delta = random.gauss(0, 0.08)
    next_week = round(pred * (1 + next_week_delta), 0)
    
    return {
        "this_week":  pred,
        "next_week":  next_week,
        "change_pct": round(next_week_delta * 100, 1),
        "method":     method,
        "confidence": "HIGH" if _is_trained else "MEDIUM",
    }


def compute_dynamic_premium(
    plan: str, zone: str, city: str,
    rain_mm: float = 0, temp_c: float = 30, aqi: float = 80,
    weeks_clean: int = 0,
) -> dict:
    """ML-enhanced dynamic premium with next-week prediction."""
    from services.db import BASE_PREMIUM, ZONE_RISK, CITY_SEASONAL, WEEKLY_CAP, MAX_CLAIMS
    
    base      = BASE_PREMIUM.get(plan, 30.0)
    zone_risk = ZONE_RISK.get(zone, 1.0)
    seasonal  = CITY_SEASONAL.get(city, 1.0)
    
    # Weather boost
    if rain_mm > 80 or temp_c > 42 or aqi > 300:
        seasonal = min(seasonal * 1.15, 1.35)
    elif rain_mm > 40 or aqi > 200:
        seasonal = min(seasonal * 1.05, 1.25)
    
    loyalty   = min(weeks_clean * 0.5, 3.0) if weeks_clean >= 8 else 0.0
    dynamic   = round(base * zone_risk * seasonal - loyalty, 2)
    
    # Next week premium prediction
    risk_d = predict_disruption_probability(rain_mm, temp_c, aqi, city, zone)
    next_mult  = 1.0 + (risk_d["probability"] - 0.3) * 0.2
    next_premium = round(dynamic * max(0.85, min(1.25, next_mult)), 2)
    
    return {
        "base":          base,
        "zone_risk":     zone_risk,
        "seasonal":      round(seasonal, 3),
        "loyalty":       loyalty,
        "dynamic":       dynamic,
        "next_week":     next_premium,
        "cap":           WEEKLY_CAP.get(plan, 200.0),
        "max_claims":    MAX_CLAIMS.get(plan, 2),
        "formula":       f"₹{base} × {zone_risk} (zone) × {round(seasonal,3)} (seasonal) − ₹{loyalty} = ₹{dynamic}",
        "risk_adjusted": risk_d["risk_level"],
    }


def _recommendation(level: str) -> str:
    return {
        "CRITICAL": "⚠️ Stop shift immediately — dangerous conditions",
        "HIGH":     "🔴 Consider ending shift — high disruption risk",
        "MEDIUM":   "🟡 Stay alert — moderate weather risk",
        "LOW":      "🟢 Safe to work — low disruption risk",
    }.get(level, "Stay safe")


def get_model_status() -> dict:
    return {
        "ml_available":    ML_AVAILABLE,
        "models_trained":  _is_trained,
        "risk_model":      "RandomForest (100 trees)" if _is_trained else "Rule-Based Fallback",
        "earnings_model":  "GradientBoosting (100 est.)" if _is_trained else "Rule-Based Fallback",
        "training_samples": 2000 if _is_trained else 0,
    }
