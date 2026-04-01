import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.db import db, row_to_dict, rows_to_list, now_iso, cur_week, audit
from services.logic import get_weather, evaluate_triggers, compute_fraud_score, calculate_claim
from services.auth_deps import require_kyc, get_current_worker

router = APIRouter()

class TriggerReq(BaseModel):
    rain_mm: Optional[float] = None
    temp_c:  Optional[float] = None
    aqi:     Optional[int]   = None

@router.post("/trigger")
async def fire_trigger(req:TriggerReq, w:dict=Depends(require_kyc)):
    with db() as conn:
        pol = row_to_dict(conn.execute("SELECT * FROM policies WHERE worker_id=?", (w["id"],)).fetchone())
    if not pol or pol["status"]!="ACTIVE":
        raise HTTPException(403,"Policy not active")

    weather = await get_weather(w["city"])
    if req.rain_mm is not None: weather["rain_mm"]=req.rain_mm; weather["source"]="simulated"
    if req.temp_c  is not None: weather["temp_c"] =req.temp_c;  weather["source"]="simulated"
    if req.aqi     is not None: weather["aqi"]    =req.aqi;     weather["source"]="simulated"

    active_triggers = evaluate_triggers(weather["rain_mm"],weather["temp_c"],weather["aqi"])
    if not active_triggers:
        return {"triggered":False,"weather":weather,"message":"No threshold crossed. Conditions are safe.","active_triggers":[]}

    with db() as conn:
        shift = row_to_dict(conn.execute("SELECT * FROM shifts WHERE worker_id=? AND status='ACTIVE'", (w["id"],)).fetchone())
        if not shift:
            return {"triggered":True,"weather":weather,"active_triggers":active_triggers,
                    "claim_generated":False,"message":"Thresholds crossed — start a shift to be eligible."}

        wk = cur_week()
        used_row = conn.execute("SELECT trigger_type FROM claims WHERE worker_id=? AND week_id=? AND status!='BLOCKED'", (w["id"],wk)).fetchall()
        used = {r["trigger_type"] for r in used_row}
        w_count = conn.execute("SELECT COUNT(*) as c FROM claims WHERE worker_id=? AND week_id=? AND status IN ('APPROVED','PAID')", (w["id"],wk)).fetchone()["c"]
        w_paid  = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM claims WHERE worker_id=? AND week_id=? AND status IN ('APPROVED','PAID')", (w["id"],wk)).fetchone()["s"]

        created = []
        for trig in active_triggers:
            if w_count>=pol["max_claims"] or w_paid>=pol["weekly_cap"] or trig["type"] in used: continue
            fraud  = compute_fraud_score(shift.get("gps_points") or 45, shift.get("active_minutes") or 120, shift.get("avg_speed") or 20.0, 180)
            calc   = calculate_claim(pol["predicted_earnings"], trig["hours"], trig["mult"])
            final  = round(min(calc["raw_amount"], pol["weekly_cap"]-w_paid), 2)
            status = "BLOCKED" if fraud["verdict"]=="AUTO_REJECTED" else "MANUAL_REVIEW" if fraud["verdict"]=="MANUAL_REVIEW" else "APPROVED"
            cur = conn.execute("INSERT INTO claims(worker_id,shift_id,trigger_type,trigger_label,trigger_value,multiplier,hours,raw_amount,amount,formula,fraud_score,fraud_flags,status,week_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (w["id"],shift["id"],trig["type"],trig["label"],trig["val"],trig["mult"],trig["hours"],calc["raw_amount"],final,calc["formula"],fraud["score"],json.dumps(fraud["flags"]),status,wk,now_iso()))
            cid = cur.lastrowid
            w_paid+=final; w_count+=1; used.add(trig["type"])
            created.append({"id":cid,"trigger_type":trig["type"],"trigger_label":trig["label"],"amount":final,"formula":calc["formula"],"fraud_score":fraud["score"],"status":status})
            audit("CLAIM", w["id"], f"type={trig['type']} amount={final} status={status}")

    return {"triggered":True,"weather":weather,"active_triggers":active_triggers,
            "claim_generated":bool(created),"claims":created,
            "message":f"{len(created)} claim(s) approved. Payout on Friday 23:59." if created else "Weekly limit reached."}

@router.get("")
def get_claims(w:dict=Depends(get_current_worker)):
    with db() as conn:
        return rows_to_list(conn.execute("SELECT * FROM claims WHERE worker_id=? ORDER BY created_at DESC", (w["id"],)).fetchall())

@router.get("/week")
def week_claims(w:dict=Depends(get_current_worker)):
    wk = cur_week()
    with db() as conn:
        claims = rows_to_list(conn.execute("SELECT * FROM claims WHERE worker_id=? AND week_id=? ORDER BY created_at DESC", (w["id"],wk)).fetchall())
        total  = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM claims WHERE worker_id=? AND week_id=? AND status IN ('APPROVED','PAID')", (w["id"],wk)).fetchone()["s"]
    return {"week_id":wk,"claims":claims,"total":total,"count":len(claims)}
