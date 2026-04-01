from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.db import db, row_to_dict
from services.logic import read_token

security = HTTPBearer(auto_error=False)

def get_current_worker(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    data = read_token(creds.credentials)
    if not data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    wid = data.get("worker_id")
    if not wid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Worker not found")
    with db() as conn:
        w = row_to_dict(conn.execute("SELECT * FROM workers WHERE id=?", (wid,)).fetchone())
    if not w:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Worker not found")
    return w

def require_kyc(w: dict = Depends(get_current_worker)) -> dict:
    with db() as conn:
        kyc = row_to_dict(conn.execute("SELECT * FROM kyc WHERE worker_id=?", (w["id"],)).fetchone())
    if not kyc or kyc["status"] != "VERIFIED":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "KYC verification required")
    return w
