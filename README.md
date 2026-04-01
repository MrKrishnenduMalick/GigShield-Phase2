# 🛡️ GigShield v5.0
### AI-Powered Parametric Micro-Insurance for India's Gig Delivery Workers

[![Python](https://img.shields.io/badge/Python-3.9%20→%203.13-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Async-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/Database-SQLite-orange)](https://sqlitebrowser.org)
[![Leaflet](https://img.shields.io/badge/Map-Leaflet.js-brightgreen)](https://leafletjs.com)
[![Guidewire](https://img.shields.io/badge/Guidewire-DEVTrails%202026-purple)](https://devtrails.guidewire.com)

> **15 million gig workers. Less than 2% insured. Zero forms. Fully automated.**

---

## ⚡ One Command — Full System

```bash
cd gigshield/backend
pip install -r requirements.txt
python main.py
```

Open: **http://localhost:8000**

That's it. Frontend + Backend + Database — all from one URL.

---

## 🗄️ Database

The database `gigshield.db` is created automatically in `backend/` on first run.

### View Database (3 options)

**Option 1 — DB Browser for SQLite (recommended)**
```
1. Download: https://sqlitebrowser.org
2. File → Open Database → backend/gigshield.db
3. Browse Data tab → select any table
```

**Option 2 — Terminal**
```bash
cd gigshield/backend
sqlite3 gigshield.db

.tables                         # list all tables
SELECT * FROM workers;          # all workers
SELECT * FROM claims;           # all claims
SELECT * FROM policies;         # all policies
SELECT * FROM audit_log;        # full audit trail
SELECT * FROM risk_events;      # AI risk scan history
.quit
```

**Option 3 — VS Code**
```
Install "SQLite Viewer" extension → open gigshield.db
```

### Database Tables

| Table | Contents |
|-------|---------|
| `workers` | Registered delivery partners |
| `kyc` | KYC docs (Aadhaar/PAN masked) |
| `policies` | Insurance policies + AI premium |
| `shifts` | GPS shift sessions + location |
| `claims` | Auto-generated disruption claims |
| `payouts` | Friday UPI payout records |
| `transactions` | Wallet transaction history |
| `risk_events` | AI risk scan log |
| `audit_log` | Complete audit trail |
| `otp_store` | Temporary OTP storage |

---

## 🎬 Demo Flow

```
1.  http://localhost:8000
2.  Enter any 10-digit phone → Send OTP
3.  Copy OTP from terminal → Verify
4.  Register: name, city, zone, plan
5.  KYC: any 12-digit Aadhaar + 10-char PAN
6.  Dashboard shows AI-calculated dynamic premium
7.  Start Shift → GPS location auto-requested
8.  Live Map tab → see your position + risk circle
9.  AI Risk panel shows live score + factors
10. Simulator tab → Fire rain trigger → Claim auto-generated ✨
11. Process Payout → UPI reference generated
12. Admin: /api/admin/stats?admin=admin2026
```

---

## 🤖 AI Systems

### 1. Dynamic Premium Engine
```
premium = base × zone_risk × weather_factor − loyalty_discount

Mumbai · Bandra · monsoon:    ₹30 × 1.30 × 1.20 − ₹0 = ₹46.80/week
Bangalore · Whitefield:        ₹30 × 0.98 × 1.05 − ₹0 = ₹30.87/week
```

### 2. Live Risk Scorer (`ai/risk_model.py`)
```
Inputs: zone, city, rain_mm, temp_c, aqi, shift_hours, claims_history
Output: risk_score (0–100), risk_level, recommendation

Score < 30  → LOW      🟢 Safe to work
Score 30–59 → MEDIUM   🟡 Stay alert
Score 60–79 → HIGH     🔴 Consider ending shift
Score 80+   → CRITICAL ⚠️ Stop shift immediately
```

### 3. Auto-Trigger Engine (`ai/trigger.py`)
```
Runs as BackgroundTask when worker updates location
If risk_score >= 65 AND active triggers exist:
  → Auto-generate claims (zero touch)
  → Log to risk_events table
  → Notify worker instantly
```

### 4. Fraud Detection (`ai/fraud.py`)
```
Checks: claim velocity, amount anomaly, repeated blocks, GPS fraud
Score < 40  → AUTO_APPROVED
Score 40–69 → MANUAL_REVIEW
Score 70+   → AUTO_REJECTED
```

---

## ⚡ Parametric Triggers

| Trigger | Threshold | Multiplier |
|---------|-----------|-----------|
| 🌧️ Heavy Rain | >80mm/hr | 1.0× |
| 🌦️ Moderate Rain | >40mm/hr | 0.6× |
| 🌡️ Extreme Heat | >42°C | 1.0× |
| 😷 Severe AQI | >300 | 1.0× |
| 🌊 Urban Flood | >150mm/hr | 1.5× |

---

## 💰 Claim Formula

```
claim = 0.5 × (predicted_weekly / 6) × hours_lost × severity_multiplier
```

---

## 🏗️ Project Structure

```
gigshield/
├── backend/
│   ├── main.py                    ← ONE COMMAND: python main.py
│   ├── requirements.txt           ← Python 3.9–3.13 compatible
│   ├── gigshield.db               ← SQLite database (auto-created)
│   ├── ai/
│   │   ├── risk_model.py          ← Live risk scorer (0–100)
│   │   ├── trigger.py             ← Auto-claim trigger engine
│   │   └── fraud.py               ← Fraud pattern detection
│   ├── routes/
│   │   ├── auth.py                ← OTP · login · register
│   │   ├── kyc.py                 ← KYC submit + verify
│   │   ├── worker.py              ← Profile · policy
│   │   ├── shifts.py              ← Start · end · GPS
│   │   ├── claims.py              ← Zero-touch trigger + claims
│   │   ├── payout.py              ← Friday batch payout
│   │   ├── location.py            ← Live location + risk scan
│   │   ├── weather.py             ← Real weather + triggers
│   │   └── admin.py               ← Stats · audit · workers
│   └── services/
│       ├── db.py                  ← SQLite schema + migration
│       ├── logic.py               ← Premium · fraud · weather
│       └── auth_deps.py           ← JWT dependencies
├── frontend/
│   └── index.html                 ← Full SPA (Leaflet map + AI risk)
├── .env.example                   ← Copy to .env
├── .gitignore
└── README.md
```

---

## 🔐 Environment Variables

```bash
cp .env.example .env
```

| Variable | Default | Required? |
|----------|---------|-----------|
| `JWT_SECRET` | built-in | Recommended to change |
| `ADMIN_SECRET` | `admin2026` | Optional |
| `OWM_API_KEY` | empty | Optional (mock works) |
| `FAST2SMS_KEY` | empty | Optional (terminal OTP) |
| `RAZORPAY_KEY_ID` | empty | Optional (simulated) |

---

## 📡 API Reference

Interactive docs: **http://localhost:8000/docs**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/send-otp` | Send OTP to phone |
| POST | `/api/auth/verify-otp` | Verify OTP + login |
| POST | `/api/auth/register` | Register + create policy |
| POST | `/api/kyc/submit` | Submit KYC |
| GET | `/api/me` | Worker profile + policy |
| POST | `/api/shifts/start` | Start delivery shift |
| POST | `/api/shifts/end` | End shift + fraud score |
| POST | `/api/claims/trigger` | Fire weather trigger |
| POST | `/api/location/update` | Update GPS + AI scan |
| GET | `/api/risk/live` | Live risk score |
| POST | `/api/payout` | Process weekly payout |
| GET | `/api/weather/{city}` | City weather + triggers |
| GET | `/api/admin/stats?admin=admin2026` | Platform stats |

---

## 👥 Team — Guidewire DEVTrails 2026

| Name | Role |
|------|------|
| Saheli Roy | Backend Development |
| Krishnendu Malick | AI & Backend |
| Rishav Kumar | Frontend & UI/UX |
| Aniket Das | Frontend Development |
| Rishika Singhadeo | UI/UX Design |

---

*GigShield — Protecting India's delivery backbone, one week at a time.*
