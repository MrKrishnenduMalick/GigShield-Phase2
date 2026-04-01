import random
from fastapi import APIRouter, HTTPException, Depends
from services.db import db, row_to_dict, rows_to_list, now_iso, audit
from services.logic import compute_fraud_score
from services.auth_deps import require_kyc, get_current_worker

router = APIRouter()

@router.post("/start")
def start_shift(w:dict=Depends(require_kyc)):
    with db() as conn:
        if conn.execute("SELECT id FROM shifts WHERE worker_id=? AND status='ACTIVE'", (w["id"],)).fetchone():
            raise HTTPException(400,"Shift already active")
        pol = row_to_dict(conn.execute("SELECT * FROM policies WHERE worker_id=?", (w["id"],)).fetchone())
        if not pol or pol["status"]!="ACTIVE":
            raise HTTPException(403,"Policy not active — complete KYC first")
        now = now_iso()
        cur = conn.execute("INSERT INTO shifts(worker_id,start_time,status) VALUES(?,?,?)", (w["id"],now,"ACTIVE"))
        sid = cur.lastrowid
    audit("SHIFT_START", w["id"])
    return {"success":True,"shift_id":sid,"started_at":now,"message":"Shift started. You are now covered by GigShield."}

@router.post("/end")
def end_shift(w:dict=Depends(require_kyc)):
    with db() as conn:
        shift = row_to_dict(conn.execute("SELECT * FROM shifts WHERE worker_id=? AND status='ACTIVE'", (w["id"],)).fetchone())
        if not shift: raise HTTPException(404,"No active shift")
        dur=random.randint(180,360); act=int(dur*random.uniform(0.55,0.85))
        gps=random.randint(60,200); spd=round(random.uniform(12,35),1)
        fr = compute_fraud_score(gps,act,spd,dur)
        conn.execute("UPDATE shifts SET end_time=?,active_minutes=?,gps_points=?,avg_speed=?,status=?,fraud_score=?,fraud_verdict=? WHERE id=?",
                     (now_iso(),act,gps,spd,"COMPLETED",fr["score"],fr["verdict"],shift["id"]))
    audit("SHIFT_END", w["id"], f"fraud={fr['score']} verdict={fr['verdict']}")
    return {"success":True,"shift_id":shift["id"],"active_minutes":act,
            "fraud_score":fr["score"],"fraud_verdict":fr["verdict"],"fraud_flags":fr["flags"]}

@router.get("/active")
def active_shift(w:dict=Depends(get_current_worker)):
    with db() as conn:
        s = row_to_dict(conn.execute("SELECT * FROM shifts WHERE worker_id=? AND status='ACTIVE'", (w["id"],)).fetchone())
    return {"active":bool(s),"shift":s}

@router.get("/history")
def shift_history(w:dict=Depends(get_current_worker)):
    with db() as conn:
        return rows_to_list(conn.execute("SELECT * FROM shifts WHERE worker_id=? ORDER BY start_time DESC", (w["id"],)).fetchall())
