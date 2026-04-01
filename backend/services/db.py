"""
GigShield — SQLite Database
Auto-creates gigshield.db in the backend folder.
View it with: https://sqlitebrowser.org  (free GUI)
"""
import sqlite3, os, random, string, json
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gigshield.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

def now_iso():    return datetime.utcnow().isoformat() + "Z"
def cur_week():   return datetime.utcnow().strftime("%Y-W%U")
def upi_ref():    return "UPI"  + "".join(random.choices(string.digits, k=12))
def rzp_id():     return "pay_" + "".join(random.choices(string.ascii_letters + string.digits, k=14))

def audit(action, worker_id, detail=""):
    with db() as conn:
        conn.execute("INSERT INTO audit_log(ts,action,worker_id,detail) VALUES(?,?,?,?)",
                     (now_iso(), action, worker_id, detail))

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS workers(
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            phone          TEXT UNIQUE NOT NULL,
            city           TEXT NOT NULL,
            zone           TEXT NOT NULL,
            vehicle_type   TEXT NOT NULL,
            platform       TEXT NOT NULL,
            weeks_clean    INTEGER DEFAULT 0,
            wallet_balance REAL    DEFAULT 0.0,
            status         TEXT    DEFAULT 'ACTIVE',
            created_at     TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS otp_store(
            phone    TEXT PRIMARY KEY,
            otp      TEXT,
            expires  REAL,
            attempts INTEGER DEFAULT 0,
            verified INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sessions(
            token     TEXT PRIMARY KEY,
            worker_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS kyc(
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id        INTEGER UNIQUE NOT NULL REFERENCES workers(id),
            status           TEXT DEFAULT 'PENDING',
            full_name        TEXT,
            phone            TEXT,
            aadhaar_masked   TEXT,
            pan_masked       TEXT,
            submitted_at     TEXT,
            verified_at      TEXT,
            rejection_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS policies(
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id          INTEGER UNIQUE NOT NULL REFERENCES workers(id),
            plan               TEXT NOT NULL,
            status             TEXT DEFAULT 'PENDING_KYC',
            base_premium       REAL,
            dynamic_premium    REAL,
            premium_formula    TEXT,
            weekly_cap         REAL,
            max_claims         INTEGER,
            predicted_earnings REAL,
            risk_score         INTEGER,
            risk_level         TEXT,
            zone_risk          REAL,
            seasonal_factor    REAL,
            loyalty_discount   REAL,
            week_start         TEXT,
            created_at         TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shifts(
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id      INTEGER NOT NULL REFERENCES workers(id),
            start_time     TEXT NOT NULL,
            end_time       TEXT,
            active_minutes INTEGER DEFAULT 0,
            gps_points     INTEGER DEFAULT 0,
            avg_speed      REAL    DEFAULT 0.0,
            status         TEXT    DEFAULT 'ACTIVE',
            fraud_score    INTEGER DEFAULT 0,
            fraud_verdict  TEXT
        );
        CREATE TABLE IF NOT EXISTS claims(
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id     INTEGER NOT NULL REFERENCES workers(id),
            shift_id      INTEGER NOT NULL REFERENCES shifts(id),
            trigger_type  TEXT NOT NULL,
            trigger_label TEXT,
            trigger_value REAL,
            multiplier    REAL,
            hours         REAL,
            raw_amount    REAL,
            amount        REAL,
            formula       TEXT,
            fraud_score   INTEGER DEFAULT 0,
            fraud_flags   TEXT    DEFAULT '[]',
            status        TEXT    DEFAULT 'APPROVED',
            week_id       TEXT,
            created_at    TEXT NOT NULL,
            paid_at       TEXT
        );
        CREATE TABLE IF NOT EXISTS payouts(
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id    INTEGER NOT NULL REFERENCES workers(id),
            week_id      TEXT,
            total_claimed REAL,
            cap          REAL,
            amount       REAL,
            claims_count INTEGER,
            upi_ref      TEXT,
            razorpay_id  TEXT,
            status       TEXT DEFAULT 'PROCESSED',
            created_at   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transactions(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id   INTEGER NOT NULL REFERENCES workers(id),
            type        TEXT,
            amount      REAL,
            description TEXT,
            ref         TEXT,
            status      TEXT DEFAULT 'SUCCESS',
            created_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log(
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            action    TEXT NOT NULL,
            worker_id INTEGER,
            detail    TEXT DEFAULT ''
        );
        """)
    print(f"[GigShield] Database ready → {DB_PATH}")

# ── CONSTANTS ────────────────────────────────────────────────
ZONE_RISK     = {"Bandra":1.30,"Andheri":1.22,"Salt Lake":1.18,"T Nagar":1.12,
                 "Koramangala":1.08,"Sector 18":1.05,"Connaught Place":1.04,
                 "Jubilee Hills":1.02,"Dharavi":1.30,"Whitefield":0.98,"Dwarka":1.10}
CITY_SEASONAL = {"Mumbai":1.20,"Kolkata":1.15,"Chennai":1.10,"Delhi":1.08,
                 "Bangalore":1.05,"Hyderabad":1.04,"Noida":1.06}
BASE_PREMIUM  = {"Basic":20.0,"Standard":30.0,"Premium":50.0}
WEEKLY_CAP    = {"Basic":150.0,"Standard":200.0,"Premium":300.0}
MAX_CLAIMS    = {"Basic":1,"Standard":2,"Premium":3}
VEHICLE_RISK  = {"Bicycle":25,"Motorcycle":15,"Scooter":18,"Car":8}
PLATFORM_RISK = {"Zepto":20,"Blinkit":18,"Swiggy":15,"Zomato":15}
CITY_COORDS   = {"Mumbai":(19.076,72.877),"Kolkata":(22.572,88.363),
                 "Delhi":(28.613,77.209),"Chennai":(13.082,80.270),
                 "Bangalore":(12.971,77.594),"Hyderabad":(17.385,78.486),"Noida":(28.535,77.391)}
MOCK_WEATHER  = {"Mumbai":{"rain_mm":14.0,"temp_c":30.0,"aqi":88,"condition":"Partly Cloudy","humidity":82},
                 "Kolkata":{"rain_mm":9.0,"temp_c":32.0,"aqi":125,"condition":"Humid","humidity":88},
                 "Delhi":{"rain_mm":0.0,"temp_c":39.0,"aqi":215,"condition":"Hazy","humidity":45},
                 "Chennai":{"rain_mm":4.0,"temp_c":34.0,"aqi":92,"condition":"Sunny","humidity":75},
                 "Bangalore":{"rain_mm":6.0,"temp_c":27.0,"aqi":78,"condition":"Cloudy","humidity":70},
                 "Hyderabad":{"rain_mm":2.0,"temp_c":36.0,"aqi":98,"condition":"Clear","humidity":55},
                 "Noida":{"rain_mm":0.0,"temp_c":38.0,"aqi":198,"condition":"Hazy","humidity":42}}


# ── DB MIGRATION: add new columns if they don't exist ────────
def migrate_db():
    """Safe migration — adds new columns to existing database."""
    with db() as conn:
        # Add location to shifts
        try:
            conn.execute("ALTER TABLE shifts ADD COLUMN latitude  REAL")
            conn.execute("ALTER TABLE shifts ADD COLUMN longitude REAL")
            conn.execute("ALTER TABLE shifts ADD COLUMN location_city TEXT")
        except Exception: pass
        # Add live risk to workers
        try:
            conn.execute("ALTER TABLE workers ADD COLUMN live_risk_score INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE workers ADD COLUMN live_weather    TEXT")
            conn.execute("ALTER TABLE workers ADD COLUMN last_location   TEXT")
        except Exception: pass
        # New table: risk_events
        conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_events(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id   INTEGER NOT NULL REFERENCES workers(id),
            shift_id    INTEGER REFERENCES shifts(id),
            event_type  TEXT NOT NULL,
            risk_score  INTEGER,
            weather_data TEXT,
            location    TEXT,
            auto_triggered INTEGER DEFAULT 0,
            claim_id    INTEGER,
            created_at  TEXT NOT NULL
        )""")
