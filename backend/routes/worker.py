from fastapi import APIRouter, Depends
from services.db import db, row_to_dict, rows_to_list, cur_week
from services.auth_deps import get_current_worker

router = APIRouter()

@router.get("/me")
def get_me(w:dict=Depends(get_current_worker)):
    wk = cur_week()
    with db() as conn:
        kyc  = row_to_dict(conn.execute("SELECT * FROM kyc WHERE worker_id=?", (w["id"],)).fetchone())
        pol  = row_to_dict(conn.execute("SELECT * FROM policies WHERE worker_id=?", (w["id"],)).fetchone())
        wc   = conn.execute("SELECT SUM(amount) as total, COUNT(*) as cnt FROM claims WHERE worker_id=? AND week_id=? AND status IN ('APPROVED','PAID')", (w["id"],wk)).fetchone()
        rt   = rows_to_list(conn.execute("SELECT * FROM transactions WHERE worker_id=? ORDER BY created_at DESC LIMIT 5", (w["id"],)).fetchall())
    return {"worker":w,"kyc":kyc,"policy":pol,
            "week_summary":{"week_id":wk,"total":wc["total"] or 0,"count":wc["cnt"] or 0},
            "recent_transactions":rt}

@router.get("/policy")
def get_policy(w:dict=Depends(get_current_worker)):
    with db() as conn:
        pol = row_to_dict(conn.execute("SELECT * FROM policies WHERE worker_id=?", (w["id"],)).fetchone())
    return pol or {}
