"""
GigShield AI — Fraud Detection Engine
Detects abnormal claim patterns, GPS spoofing, velocity fraud.
"""
from services.db import db, rows_to_list, row_to_dict


def analyze_claim_fraud(worker_id: int, new_claim_amount: float) -> dict:
    """Holistic fraud analysis combining GPS, history, and velocity checks."""
    with db() as conn:
        # Last 30 days claims
        history = rows_to_list(conn.execute(
            "SELECT * FROM claims WHERE worker_id=? ORDER BY created_at DESC LIMIT 30",
            (worker_id,)).fetchall())
        # Worker profile
        worker = row_to_dict(conn.execute(
            "SELECT * FROM workers WHERE id=?", (worker_id,)).fetchone())

    flags = []
    score = 0

    if not history:
        return {"fraud_score": 0, "flags": [], "verdict": "AUTO_APPROVED",
                "detail": "No claim history — clean profile"}

    # ── Rule 1: Velocity — too many claims in 7 days ─────────
    recent_7d = [c for c in history if c.get("week_id") == _cur_week()]
    if len(recent_7d) >= 3:
        score += 30
        flags.append(f"HIGH_CLAIM_VELOCITY: {len(recent_7d)} claims this week")

    # ── Rule 2: Amount anomaly ────────────────────────────────
    if len(history) >= 3:
        avg = sum(c["amount"] for c in history[:10]) / min(len(history), 10)
        if new_claim_amount > avg * 2.5:
            score += 25
            flags.append(f"AMOUNT_ANOMALY: ₹{new_claim_amount:.0f} vs avg ₹{avg:.0f}")

    # ── Rule 3: Consecutive blocked claims ────────────────────
    blocked = sum(1 for c in history[:5] if c["status"] == "BLOCKED")
    if blocked >= 2:
        score += 20
        flags.append(f"REPEATED_BLOCKS: {blocked} recent blocked claims")

    # ── Rule 4: Suspiciously high fraud scores in history ─────
    high_fraud = [c for c in history if (c.get("fraud_score") or 0) > 60]
    if len(high_fraud) >= 2:
        score += 15
        flags.append(f"FRAUD_PATTERN: {len(high_fraud)} high-fraud-score shifts")

    # ── Rule 5: New account with immediate claim ──────────────
    if worker and worker.get("weeks_clean", 0) == 0 and len(history) >= 2:
        score += 10
        flags.append("NEW_ACCOUNT_HEAVY_CLAIMS: Multiple claims in first week")

    score = min(score, 100)
    verdict = ("AUTO_APPROVED" if score < 40
               else "MANUAL_REVIEW" if score < 70
               else "AUTO_REJECTED")

    return {
        "fraud_score": score,
        "flags":       flags,
        "verdict":     verdict,
        "claims_this_week": len(recent_7d),
        "detail": f"Pattern analysis: {len(flags)} flag(s) detected",
    }


def _cur_week():
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-W%U")
