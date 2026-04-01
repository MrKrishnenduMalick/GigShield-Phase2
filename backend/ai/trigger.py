"""
GigShield AI — Auto Trigger Engine
Monitors active shifts and fires claims automatically when thresholds crossed.
Runs as FastAPI BackgroundTask.
"""
import json
from services.db import db, row_to_dict, rows_to_list, now_iso, cur_week, audit
from services.logic import get_weather, evaluate_triggers, calculate_claim, compute_fraud_score
from ai.risk_model import compute_risk_score


async def run_auto_trigger_for_worker(worker_id: int) -> dict:
    """
    Called as a BackgroundTask when:
    - Worker starts a shift
    - Worker updates location
    - Periodic monitor fires

    Returns: dict with trigger results
    """
    with db() as conn:
        worker = row_to_dict(conn.execute(
            "SELECT * FROM workers WHERE id=?", (worker_id,)).fetchone())
        if not worker:
            return {"triggered": False, "reason": "Worker not found"}

        shift = row_to_dict(conn.execute(
            "SELECT * FROM shifts WHERE worker_id=? AND status='ACTIVE'", (worker_id,)).fetchone())
        if not shift:
            return {"triggered": False, "reason": "No active shift"}

        pol = row_to_dict(conn.execute(
            "SELECT * FROM policies WHERE worker_id=?", (worker_id,)).fetchone())
        if not pol or pol["status"] != "ACTIVE":
            return {"triggered": False, "reason": "Policy not active"}

    # Fetch live weather
    weather = await get_weather(worker["city"])
    active_triggers = evaluate_triggers(weather["rain_mm"], weather["temp_c"], weather["aqi"])

    if not active_triggers:
        return {"triggered": False, "weather": weather, "reason": "No thresholds crossed"}

    # Compute AI risk score
    risk = compute_risk_score(
        zone      = worker["zone"],
        city      = worker["city"],
        rain_mm   = weather["rain_mm"],
        temp_c    = weather["temp_c"],
        aqi       = weather["aqi"],
        shift_hours = (shift.get("active_minutes") or 0) / 60,
    )

    # Log the risk event
    with db() as conn:
        conn.execute(
            "INSERT INTO risk_events(worker_id,shift_id,event_type,risk_score,weather_data,auto_triggered,created_at) VALUES(?,?,?,?,?,?,?)",
            (worker_id, shift["id"], "AUTO_SCAN", risk["risk_score"],
             json.dumps(weather), 1, now_iso())
        )
        # Update worker live risk
        conn.execute("UPDATE workers SET live_risk_score=?,live_weather=? WHERE id=?",
                     (int(risk["risk_score"]), json.dumps(weather), worker_id))

    if not risk["should_auto_trigger"]:
        return {
            "triggered":  False,
            "risk_score": risk["risk_score"],
            "weather":    weather,
            "reason":     f"Risk {risk['risk_score']}/100 below auto-trigger threshold (65)",
        }

    # Auto-generate claims
    created = []
    with db() as conn:
        wk       = cur_week()
        used     = {r["trigger_type"] for r in conn.execute(
            "SELECT trigger_type FROM claims WHERE worker_id=? AND week_id=? AND status!='BLOCKED'",
            (worker_id, wk)).fetchall()}
        w_count  = conn.execute(
            "SELECT COUNT(*) as c FROM claims WHERE worker_id=? AND week_id=? AND status IN ('APPROVED','PAID')",
            (worker_id, wk)).fetchone()["c"]
        w_paid   = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM claims WHERE worker_id=? AND week_id=? AND status IN ('APPROVED','PAID')",
            (worker_id, wk)).fetchone()["s"]

        for trig in active_triggers:
            if w_count >= pol["max_claims"] or w_paid >= pol["weekly_cap"]:
                break
            if trig["type"] in used:
                continue

            fraud  = compute_fraud_score(
                shift.get("gps_points") or 45,
                shift.get("active_minutes") or 120,
                shift.get("avg_speed") or 20.0, 180)
            calc   = calculate_claim(pol["predicted_earnings"], trig["hours"], trig["mult"])
            final  = round(min(calc["raw_amount"], pol["weekly_cap"] - w_paid), 2)
            status = ("BLOCKED" if fraud["verdict"] == "AUTO_REJECTED"
                      else "MANUAL_REVIEW" if fraud["verdict"] == "MANUAL_REVIEW"
                      else "APPROVED")

            cur = conn.execute(
                """INSERT INTO claims(worker_id,shift_id,trigger_type,trigger_label,trigger_value,
                   multiplier,hours,raw_amount,amount,formula,fraud_score,fraud_flags,status,week_id,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (worker_id, shift["id"], trig["type"], trig["label"], trig["val"],
                 trig["mult"], trig["hours"], calc["raw_amount"], final,
                 calc["formula"], fraud["score"], json.dumps(fraud["flags"]),
                 status, wk, now_iso()))
            cid = cur.lastrowid
            w_paid  += final
            w_count += 1
            used.add(trig["type"])
            created.append({
                "claim_id": cid, "trigger": trig["type"],
                "label": trig["label"], "amount": final, "status": status,
            })
            audit("AUTO_CLAIM", worker_id,
                  f"AI auto-trigger: {trig['type']} risk={risk['risk_score']} amount={final}")

    return {
        "triggered":   bool(created),
        "risk_score":  risk["risk_score"],
        "risk_level":  risk["risk_level"],
        "weather":     weather,
        "claims":      created,
        "message":     (f"AI auto-generated {len(created)} claim(s) — Risk score {risk['risk_score']}/100"
                        if created else "Triggers active but no new claims generated"),
    }
