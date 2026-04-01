import os
from fastapi import APIRouter, HTTPException, Query
from services.db import db, rows_to_list, row_to_dict
router = APIRouter()
ADMIN_SECRET = os.getenv("ADMIN_SECRET","admin2026")

def _check(s): 
    if s!=ADMIN_SECRET: raise HTTPException(403,"Admin access required — use ?admin=admin2026")

@router.get("/stats")
def admin_stats(admin:str=Query("")):
    _check(admin)
    with db() as conn:
        workers  = conn.execute("SELECT COUNT(*) as c FROM workers").fetchone()["c"]
        verified = conn.execute("SELECT COUNT(*) as c FROM kyc WHERE status='VERIFIED'").fetchone()["c"]
        pending  = conn.execute("SELECT COUNT(*) as c FROM kyc WHERE status='PENDING'").fetchone()["c"]
        active_p = conn.execute("SELECT COUNT(*) as c FROM policies WHERE status='ACTIVE'").fetchone()["c"]
        t_claims = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
        a_claims = conn.execute("SELECT COUNT(*) as c FROM claims WHERE status='APPROVED'").fetchone()["c"]
        p_claims = conn.execute("SELECT COUNT(*) as c FROM claims WHERE status='PAID'").fetchone()["c"]
        b_claims = conn.execute("SELECT COUNT(*) as c FROM claims WHERE status='BLOCKED'").fetchone()["c"]
        pool     = conn.execute("SELECT COALESCE(SUM(dynamic_premium),0) as s FROM policies WHERE status='ACTIVE'").fetchone()["s"]
        paid     = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM payouts").fetchone()["s"]
    return {"workers":workers,"kyc_verified":verified,"kyc_pending":pending,
            "active_policies":active_p,"total_claims":t_claims,"approved_claims":a_claims,
            "paid_claims":p_claims,"blocked_claims":b_claims,"premium_pool":round(pool,2),
            "total_disbursed":round(paid,2),"loss_ratio":round(paid/max(pool*10,1)*100,1)}

@router.get("/workers")
def admin_workers(admin:str=Query("")):
    _check(admin)
    with db() as conn:
        ws = rows_to_list(conn.execute("SELECT w.*,k.status as kyc_status,p.status as policy_status,p.dynamic_premium FROM workers w LEFT JOIN kyc k ON k.worker_id=w.id LEFT JOIN policies p ON p.worker_id=w.id").fetchall())
    return ws

@router.get("/claims")
def admin_claims(admin:str=Query("")):
    _check(admin)
    with db() as conn:
        return rows_to_list(conn.execute("SELECT c.*,w.name as worker_name,w.city FROM claims c JOIN workers w ON w.id=c.worker_id ORDER BY c.created_at DESC").fetchall())

@router.get("/audit")
def admin_audit(admin:str=Query(""),limit:int=Query(50)):
    _check(admin)
    with db() as conn:
        return rows_to_list(conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall())
