from fastapi import APIRouter, Depends
from services.db import db, row_to_dict, rows_to_list, now_iso, cur_week, upi_ref, rzp_id, audit
from services.auth_deps import get_current_worker

router = APIRouter()

@router.post("")
def run_payout(w:dict=Depends(get_current_worker)):
    wk = cur_week()
    with db() as conn:
        claims = rows_to_list(conn.execute("SELECT * FROM claims WHERE worker_id=? AND week_id=? AND status='APPROVED'", (w["id"],wk)).fetchall())
        if not claims: return {"processed":False,"message":"No approved claims this week."}
        pol   = row_to_dict(conn.execute("SELECT * FROM policies WHERE worker_id=?", (w["id"],)).fetchone()) or {}
        cap   = pol.get("weekly_cap",200.0)
        total = sum(c["amount"] for c in claims)
        amt   = round(min(total,cap),2)
        ref   = upi_ref(); rzp = rzp_id(); now = now_iso()
        conn.execute("INSERT INTO payouts(worker_id,week_id,total_claimed,cap,amount,claims_count,upi_ref,razorpay_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (w["id"],wk,total,cap,amt,len(claims),ref,rzp,"PROCESSED",now))
        conn.execute("INSERT INTO transactions(worker_id,type,amount,description,ref,status,created_at) VALUES(?,?,?,?,?,?,?)",
                     (w["id"],"CREDIT",amt,f"Weekly payout — {len(claims)} claim(s)",ref,"SUCCESS",now))
        new_bal = round((w.get("wallet_balance",0) or 0) + amt, 2)
        conn.execute("UPDATE workers SET wallet_balance=? WHERE id=?", (new_bal,w["id"]))
        for c in claims:
            conn.execute("UPDATE claims SET status='PAID',paid_at=? WHERE id=?", (now,c["id"]))
        if not any(c["fraud_score"]>40 for c in claims):
            conn.execute("UPDATE workers SET weeks_clean=weeks_clean+1 WHERE id=?", (w["id"],))
    audit("PAYOUT", w["id"], f"amount={amt} ref={ref}")
    return {"processed":True,"amount":amt,"upi_ref":ref,"razorpay_id":rzp,
            "claims_count":len(claims),"wallet_balance":new_bal,
            "message":f"₹{amt:.0f} credited to your UPI — Ref: {ref}"}

@router.get("/history")
def payout_history(w:dict=Depends(get_current_worker)):
    with db() as conn:
        return rows_to_list(conn.execute("SELECT * FROM payouts WHERE worker_id=? ORDER BY created_at DESC", (w["id"],)).fetchall())

@router.get("/transactions")
def get_transactions(w:dict=Depends(get_current_worker)):
    with db() as conn:
        return rows_to_list(conn.execute("SELECT * FROM transactions WHERE worker_id=? ORDER BY created_at DESC", (w["id"],)).fetchall())
