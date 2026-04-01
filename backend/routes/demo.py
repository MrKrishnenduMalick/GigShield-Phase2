"""
GigShield — Demo Mode Routes (Hackathon Secret Weapon)
One-click: register demo worker, start shift, trigger rain, show claim, pay out.
"""

import json, random
from fastapi import APIRouter, BackgroundTasks
from services.db import db, row_to_dict, rows_to_list, now_iso, cur_week, upi_ref, audit, WEEKLY_CAP
from services.logic import (generate_otp, make_token, is_otp_verified,
                             calculate_premium, compute_risk_score,
                             predict_earnings, evaluate_triggers, calculate_claim,
                             compute_fraud_score)
from ml.model import predict_disruption_probability, compute_dynamic_premium, predict_weekly_earnings

router = APIRouter()

DEMO_SCENARIOS = {
    "monsoon_rain": {
        "rain_mm": 92.0, "temp_c": 28.5, "aqi": 95,
        "label": "Mumbai Monsoon 🌧️", "trigger": "HEAVY_RAIN",
        "description": "Heavy rainfall detected: 92mm/hr — Bandra zone flooding"
    },
    "heatwave": {
        "rain_mm": 0, "temp_c": 45.2, "aqi": 180,
        "label": "Delhi Heatwave 🌡️", "trigger": "EXTREME_HEAT",
        "description": "Extreme heat warning: 45.2°C — dangerous for outdoor work"
    },
    "aqi_crisis": {
        "rain_mm": 0, "temp_c": 32, "aqi": 385,
        "label": "Delhi AQI Crisis 😷", "trigger": "SEVERE_AQI",
        "description": "Air quality index: 385 (HAZARDOUS) — immediate health risk"
    },
    "urban_flood": {
        "rain_mm": 165, "temp_c": 27, "aqi": 110,
        "label": "Urban Flood 🌊", "trigger": "URBAN_FLOOD",
        "description": "Urban flooding: 165mm/hr — roads submerged, routes blocked"
    },
    "perfect_storm": {
        "rain_mm": 88, "temp_c": 38, "aqi": 220,
        "label": "Perfect Storm ⛈️", "trigger": "HEAVY_RAIN",
        "description": "Multiple triggers: heavy rain + heat + poor air quality"
    },
}


@router.post("/demo/instant")
def instant_demo(scenario: str = "monsoon_rain"):
    """
    Complete demo flow in one API call:
    1. Creates demo worker (or uses existing)
    2. Activates policy
    3. Starts shift
    4. Fires trigger scenario
    5. Generates claim
    6. Processes payout
    Returns full timeline for UI to animate step by step.
    """
    sc = DEMO_SCENARIOS.get(scenario, DEMO_SCENARIOS["monsoon_rain"])
    timeline = []

    with db() as conn:
        # Step 1: Demo worker
        demo_phone = "9999999999"
        worker = row_to_dict(conn.execute(
            "SELECT * FROM workers WHERE phone=?", (demo_phone,)).fetchone())

        if not worker:
            conn.execute(
                "INSERT INTO workers(name,phone,city,zone,vehicle_type,platform,weeks_clean,wallet_balance,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("Raju Sharma", demo_phone, "Mumbai", "Bandra", "Motorcycle", "Swiggy",
                 3, 0.0, "ACTIVE", now_iso())
            )
            worker_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

            # KYC
            conn.execute(
                "INSERT OR IGNORE INTO kyc(worker_id,status,full_name,phone,aadhaar_masked,pan_masked,submitted_at,verified_at) VALUES(?,?,?,?,?,?,?,?)",
                (worker_id, "VERIFIED", "Raju Sharma", demo_phone,
                 "XXXX-XXXX-1234", "ABD*****2Z", now_iso(), now_iso())
            )

            # OTP mark verified
            conn.execute(
                "INSERT OR REPLACE INTO otp_store(phone,otp,expires,attempts,verified) VALUES(?,?,?,?,?)",
                (demo_phone, "123456", 9999999999, 0, 1)
            )
            timeline.append({"step": 1, "title": "Worker Registered",
                              "detail": "Raju Sharma — Mumbai, Bandra — Swiggy", "status": "done"})
        else:
            worker_id = worker["id"]
            timeline.append({"step": 1, "title": "Demo Worker Active",
                              "detail": f"Raju Sharma — ID #{worker_id}", "status": "done"})

        # Ensure policy
        pol = row_to_dict(conn.execute(
            "SELECT * FROM policies WHERE worker_id=?", (worker_id,)).fetchone())
        if not pol:
            p   = calculate_premium("Standard", "Bandra", "Mumbai")
            e   = predict_earnings("Mumbai", "Bandra")
            conn.execute(
                "INSERT INTO policies(worker_id,plan,status,base_premium,dynamic_premium,premium_formula,weekly_cap,max_claims,predicted_earnings,risk_score,risk_level,zone_risk,seasonal_factor,loyalty_discount,week_start,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (worker_id, "Standard", "ACTIVE", p["base"], p["dynamic"],
                 p["formula"], p["cap"], p["max_claims"], e, 55, "MEDIUM",
                 p["zone_risk"], p["seasonal"], p["loyalty"], now_iso(), now_iso())
            )
            pol = row_to_dict(conn.execute(
                "SELECT * FROM policies WHERE worker_id=?", (worker_id,)).fetchone())
        else:
            conn.execute("UPDATE policies SET status='ACTIVE' WHERE worker_id=?", (worker_id,))

        timeline.append({"step": 2, "title": "Policy Active",
                          "detail": f"Standard Plan · ₹{pol['weekly_cap']:.0f} cap · ₹{pol['dynamic_premium']:.0f}/wk",
                          "status": "done"})

        # Step 3: Active shift
        shift = row_to_dict(conn.execute(
            "SELECT * FROM shifts WHERE worker_id=? AND status='ACTIVE'", (worker_id,)).fetchone())
        if not shift:
            conn.execute(
                "INSERT INTO shifts(worker_id,start_time,active_minutes,gps_points,avg_speed,status) VALUES(?,?,?,?,?,?)",
                (worker_id, now_iso(), 127, 89, 24.3, "ACTIVE")
            )
            shift_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        else:
            shift_id = shift["id"]

        timeline.append({"step": 3, "title": "Shift Active",
                          "detail": "GPS tracking ON · 127 min active · Bandra zone",
                          "status": "done"})

    # Step 4: AI Risk Analysis
    risk = predict_disruption_probability(
        sc["rain_mm"], sc["temp_c"], sc["aqi"],
        city="Mumbai", zone="Bandra"
    )
    timeline.append({
        "step": 4, "title": "AI Risk Analysis",
        "detail": f"Risk Score: {risk['risk_score']}/100 · {risk['risk_level']} · {risk['method']}",
        "status": "done", "risk": risk
    })

    # Step 5: Trigger fires
    triggers = evaluate_triggers(sc["rain_mm"], sc["temp_c"], sc["aqi"])
    timeline.append({
        "step": 5, "title": f"Trigger Fired: {sc['label']}",
        "detail": sc["description"],
        "status": "done", "triggers": triggers
    })

    # Step 6: Fraud detection
    fraud = compute_fraud_score(89, 127, 24.3, 200)
    timeline.append({
        "step": 6, "title": "Fraud Check Passed",
        "detail": f"Score: {fraud['score']}/100 · Verdict: {fraud['verdict']}",
        "status": "done", "fraud": fraud
    })

    # Step 7: Claim generation
    claim_id = None
    claim_amount = 0.0
    with db() as conn:
        wk     = cur_week()
        w_paid = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM claims WHERE worker_id=? AND week_id=? AND status IN ('APPROVED','PAID')",
            (worker_id, wk)).fetchone()["s"]

        if triggers and w_paid < pol["weekly_cap"] and fraud["verdict"] != "AUTO_REJECTED":
            trig   = triggers[0]
            calc   = calculate_claim(pol["predicted_earnings"], trig["hours"], trig["mult"])
            final  = round(min(calc["raw_amount"], pol["weekly_cap"] - w_paid), 2)

            cur = conn.execute(
                """INSERT INTO claims(worker_id,shift_id,trigger_type,trigger_label,trigger_value,
                   multiplier,hours,raw_amount,amount,formula,fraud_score,fraud_flags,status,week_id,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (worker_id, shift_id, trig["type"], trig["label"], trig["val"],
                 trig["mult"], trig["hours"], calc["raw_amount"], final,
                 calc["formula"], fraud["score"], "[]", "APPROVED", wk, now_iso())
            )
            claim_id     = cur.lastrowid
            claim_amount = final
            audit("DEMO_CLAIM", worker_id, f"Demo claim ₹{final} scenario={scenario}")

    timeline.append({
        "step": 7, "title": "Claim Auto-Approved ✅",
        "detail": f"₹{claim_amount:.0f} — Formula: {triggers[0]['mult']}× · {triggers[0]['hours']}h disrupted",
        "status": "done", "claim_id": claim_id, "amount": claim_amount
    })

    # Step 8: Instant payout
    ref = upi_ref()
    with db() as conn:
        conn.execute(
            "INSERT INTO payouts(worker_id,week_id,total_claimed,cap,amount,claims_count,upi_ref,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (worker_id, cur_week(), claim_amount, pol["weekly_cap"], claim_amount, 1, ref, "PROCESSED", now_iso())
        )
        conn.execute(
            "INSERT INTO transactions(worker_id,type,amount,description,ref,status,created_at) VALUES(?,?,?,?,?,?,?)",
            (worker_id, "CREDIT", claim_amount, f"Demo payout — {sc['label']}", ref, "SUCCESS", now_iso())
        )
        if claim_id:
            conn.execute("UPDATE claims SET status='PAID',paid_at=? WHERE id=?", (now_iso(), claim_id))
        conn.execute("UPDATE workers SET wallet_balance=wallet_balance+? WHERE id=?", (claim_amount, worker_id))
        new_wallet = conn.execute("SELECT wallet_balance FROM workers WHERE id=?", (worker_id,)).fetchone()["wallet_balance"]

    timeline.append({
        "step": 8, "title": "UPI Payout Processed 💸",
        "detail": f"₹{claim_amount:.0f} credited · Ref: {ref}",
        "status": "done", "upi_ref": ref, "wallet": new_wallet
    })

    token = make_token({"worker_id": worker_id})
    return {
        "success":   True,
        "scenario":  sc,
        "worker_id": worker_id,
        "token":     token,
        "timeline":  timeline,
        "summary": {
            "risk_score":   risk["risk_score"],
            "claim_amount": claim_amount,
            "upi_ref":      ref,
            "scenario":     sc["label"],
            "triggers":     [t["label"] for t in triggers],
        }
    }


@router.get("/demo/scenarios")
def list_scenarios():
    return {k: {"label": v["label"], "description": v["description"]} for k, v in DEMO_SCENARIOS.items()}


@router.post("/demo/reset")
def reset_demo():
    """Reset demo worker for a clean re-run."""
    with db() as conn:
        demo_phone = "9999999999"
        worker = row_to_dict(conn.execute("SELECT id FROM workers WHERE phone=?", (demo_phone,)).fetchone())
        if worker:
            wid = worker["id"]
            conn.execute("UPDATE claims SET status='APPROVED',paid_at=NULL WHERE worker_id=? AND week_id=?", (wid, cur_week()))
            conn.execute("DELETE FROM shifts WHERE worker_id=? AND status='ACTIVE'", (wid,))
            conn.execute("UPDATE workers SET wallet_balance=0 WHERE id=?", (wid,))
    return {"reset": True, "message": "Demo reset — ready for next run"}
