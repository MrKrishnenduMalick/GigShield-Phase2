from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.db import db, row_to_dict, now_iso, audit
from services.auth_deps import get_current_worker

router = APIRouter()

class KYCReq(BaseModel):
    full_name:str; aadhaar:str; pan:str

@router.post("/submit")
def submit_kyc(req:KYCReq, w:dict=Depends(get_current_worker)):
    if not req.aadhaar.isdigit() or len(req.aadhaar)!=12:
        raise HTTPException(400,"Aadhaar must be exactly 12 digits")
    pan = req.pan.upper().strip()
    if len(pan)!=10:
        raise HTTPException(400,"PAN must be exactly 10 characters")
    with db() as conn:
        kyc = row_to_dict(conn.execute("SELECT * FROM kyc WHERE worker_id=?", (w["id"],)).fetchone())
        if not kyc: raise HTTPException(404,"KYC record not found")
        if kyc["status"]=="VERIFIED": raise HTTPException(400,"KYC already verified")
        ma = f"XXXX-XXXX-{req.aadhaar[-4:]}"; mp = f"{pan[:3]}{'*'*5}{pan[-2:]}"
        now = now_iso()
        conn.execute("UPDATE kyc SET status=?,full_name=?,aadhaar_masked=?,pan_masked=?,submitted_at=?,verified_at=? WHERE worker_id=?",
                     ("VERIFIED",req.full_name,ma,mp,now,now,w["id"]))
        conn.execute("UPDATE policies SET status=?,week_start=? WHERE worker_id=?",
                     ("ACTIVE",now,w["id"]))
    audit("KYC_VERIFIED", w["id"])
    return {"success":True,"kyc_status":"VERIFIED","aadhaar_masked":ma,"pan_masked":mp,
            "policy_status":"ACTIVE","message":"Identity verified. Your coverage is now active!"}

@router.get("/status")
def kyc_status(w:dict=Depends(get_current_worker)):
    with db() as conn:
        kyc = row_to_dict(conn.execute("SELECT * FROM kyc WHERE worker_id=?", (w["id"],)).fetchone())
    if not kyc: raise HTTPException(404,"KYC not found")
    return kyc
