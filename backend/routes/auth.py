from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from services.db import db, row_to_dict, now_iso, audit
from services.logic import (generate_otp, verify_otp, is_otp_verified,
    send_sms, make_token, calculate_premium, compute_risk_score, predict_earnings)
from services.auth_deps import get_current_worker, security

router = APIRouter()

class OTPReq(BaseModel):      phone: str
class VerifyReq(BaseModel):   phone: str; otp: str
class RegisterReq(BaseModel):
    phone:str; name:str; city:str; zone:str="Bandra"
    vehicle_type:str="Motorcycle"; platform:str="Swiggy"; plan:str="Standard"

def _clean(phone): return phone.replace("+91","").replace(" ","").strip()

@router.post("/send-otp")
async def send_otp(req: OTPReq):
    phone = _clean(req.phone)
    if not phone.isdigit() or len(phone)!=10:
        raise HTTPException(400,"Enter a valid 10-digit mobile number")
    otp = generate_otp(phone)
    await send_sms(phone, otp)
    with db() as conn:
        exists = conn.execute("SELECT id FROM workers WHERE phone=?", (phone,)).fetchone()
    return {"success":True,"message":f"OTP sent to +91-{phone}","demo_otp":otp,
            "is_registered":bool(exists),"expires_in":300}

@router.post("/verify-otp")
def verify_otp_route(req: VerifyReq):
    phone = _clean(req.phone)
    if not verify_otp(phone, req.otp):
        raise HTTPException(400,"Invalid or expired OTP")
    with db() as conn:
        w   = row_to_dict(conn.execute("SELECT * FROM workers WHERE phone=?", (phone,)).fetchone())
        if w:
            kyc = row_to_dict(conn.execute("SELECT * FROM kyc WHERE worker_id=?", (w["id"],)).fetchone())
            pol = row_to_dict(conn.execute("SELECT * FROM policies WHERE worker_id=?", (w["id"],)).fetchone())
            tok = make_token({"worker_id":w["id"],"phone":phone})
            audit("LOGIN", w["id"])
            return {"success":True,"action":"LOGIN","token":tok,"worker":w,
                    "kyc_status":kyc["status"] if kyc else "NOT_SUBMITTED","policy":pol}
    return {"success":True,"action":"REGISTER","phone":phone}

@router.post("/register")
def register(req: RegisterReq):
    phone = _clean(req.phone)
    if not is_otp_verified(phone):
        raise HTTPException(400,"Verify OTP before registering")
    with db() as conn:
        if conn.execute("SELECT id FROM workers WHERE phone=?", (phone,)).fetchone():
            raise HTTPException(400,"Account already exists — please login")
        p    = calculate_premium(req.plan, req.zone, req.city)
        risk = compute_risk_score(req.zone, req.city, req.vehicle_type, req.platform)
        pred = predict_earnings(req.city, req.zone)
        now  = now_iso()
        cur  = conn.execute(
            "INSERT INTO workers(name,phone,city,zone,vehicle_type,platform,created_at) VALUES(?,?,?,?,?,?,?)",
            (req.name,phone,req.city,req.zone,req.vehicle_type,req.platform,now))
        wid = cur.lastrowid
        conn.execute("INSERT INTO kyc(worker_id,status,full_name,phone) VALUES(?,?,?,?)",
                     (wid,"PENDING",req.name,phone))
        conn.execute("""INSERT INTO policies(worker_id,plan,status,base_premium,dynamic_premium,
            premium_formula,weekly_cap,max_claims,predicted_earnings,risk_score,risk_level,
            zone_risk,seasonal_factor,loyalty_discount,week_start,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (wid,req.plan,"PENDING_KYC",p["base"],p["dynamic"],p["formula"],
             p["cap"],p["max_claims"],pred,risk["score"],risk["level"],
             p["zone_risk"],p["seasonal"],p["loyalty"],now,now))
        tok = make_token({"worker_id":wid,"phone":phone})
        w   = row_to_dict(conn.execute("SELECT * FROM workers WHERE id=?", (wid,)).fetchone())
        pol = row_to_dict(conn.execute("SELECT * FROM policies WHERE worker_id=?", (wid,)).fetchone())
    audit("REGISTER", wid, f"plan={req.plan} city={req.city}")
    return {"success":True,"token":tok,"worker":w,"kyc_status":"PENDING","policy":pol,
            "message":f"Welcome to GigShield, {req.name}! Complete KYC to activate coverage."}

@router.post("/logout")
def logout(w:dict=Depends(get_current_worker), creds:HTTPAuthorizationCredentials=Depends(security)):
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (creds.credentials,))
    audit("LOGOUT", w["id"])
    return {"success":True}
