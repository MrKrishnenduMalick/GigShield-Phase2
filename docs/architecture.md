# GigShield — System Architecture

## Stack
- **Backend:** Python 3.9+ · FastAPI · Uvicorn (runs locally)
- **Frontend:** Vanilla HTML/CSS/JS (single file, no build step)
- **Database:** In-memory Python dict (zero setup, swap for PostgreSQL in production)
- **Auth:** JWT (python-jose) · OTP via terminal (or Fast2SMS)

## Folder Structure
```
gigshield/
├── backend/
│   ├── main.py                    ← FastAPI entry point
│   ├── requirements.txt
│   ├── routes/                    ← One file per feature
│   │   ├── auth.py                ← OTP · login · register · logout
│   │   ├── kyc.py                 ← KYC submit + status
│   │   ├── worker.py              ← /me · /policy
│   │   ├── shifts.py              ← start · end · history
│   │   ├── claims.py              ← trigger evaluation + auto-claims
│   │   ├── payout.py              ← weekly payout batch
│   │   ├── weather.py             ← weather + trigger check
│   │   └── admin.py               ← stats · audit (admin2026)
│   └── services/
│       ├── db.py                  ← In-memory DB + constants
│       ├── logic.py               ← All business logic
│       └── auth_deps.py           ← FastAPI auth dependencies
├── frontend/
│   └── index.html                 ← Complete SPA dashboard
├── .env.example
├── .gitignore
└── README.md
```

## Payout Formula
```
claim = 0.5 × (predicted_weekly / 6) × hours_lost × severity_multiplier
```

## Trigger Thresholds
| Trigger | Threshold | Multiplier |
|---------|-----------|-----------|
| Heavy Rain | >80mm/hr | 1.0× |
| Moderate Rain | >40mm/hr | 0.6× |
| Extreme Heat | >42°C | 1.0× |
| Severe AQI | >300 | 1.0× |
| Urban Flood | >150mm/hr | 1.5× |

## Weekly Cycle
```
Saturday 00:00  →  Coverage starts
Sat to Fri      →  Disruptions accumulate as approved claims
Friday 23:59    →  POST /api/payout → one UPI transfer
Saturday 00:00  →  New week begins automatically
```
