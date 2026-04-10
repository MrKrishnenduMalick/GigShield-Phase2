from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import datetime

app = FastAPI(title="Earn Protector API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock Data Storage
users = {
    "raju": {"role": "worker", "name": "Raju"},
    "priya": {"role": "worker", "name": "Priya"},
    "admin": {"role": "admin", "name": "Admin"}
}

notifications: Dict[str, List[Dict[str, Any]]] = {
    "raju": [],
    "priya": [],
    "admin": []
}

class ClaimRequest(BaseModel):
    user_id: str
    gps_check: bool
    weather_check: bool
    delivery_check: bool

class ClaimResponse(BaseModel):
    risk_score: float
    final_decision: str
    payout: bool

# Metrics for admin
admin_metrics = {
    "total_claims": 0,
    "approved_claims": 0,
    "rejected_claims": 0,
    "warning_claims": 0,
    "average_risk_score": 0.0
}

def notify_user(user_id: str, message: str, type: str):
    if user_id in notifications:
        notifications[user_id].insert(0, {
            "timestamp": datetime.datetime.now().isoformat(),
            "message": message,
            "type": type
        })

@app.post("/api/login")
def login(username: str):
    user = users.get(username.lower())
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": username.lower(), "role": user["role"], "name": user["name"]}

@app.post("/api/simulate_claim_checks", response_model=ClaimResponse)
def simulate_claim_checks(request: ClaimRequest):
    if request.user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")

    # Simple Risk Engine Logic
    risk_score = 0.0
    # Simulate realistic logic
    if not request.gps_check: risk_score += 0.35
    if not request.weather_check: risk_score += 0.25
    if not request.delivery_check: risk_score += 0.40
    
    # Base risk factor
    risk_score += 0.1 

    # Ensure risk score is capped
    risk_score = min(risk_score, 1.0)
    
    if risk_score < 0.4:
        decision = "approved"
        payout = True
    elif risk_score >= 0.4 and risk_score < 0.7:
        decision = "warning"
        payout = False
    else:
        decision = "rejected"
        payout = False

    # Update Admin Metrics
    admin_metrics["total_claims"] += 1
    if decision == "approved":
        admin_metrics["approved_claims"] += 1
    elif decision == "warning":
        admin_metrics["warning_claims"] += 1
    else:
        admin_metrics["rejected_claims"] += 1
    
    # Running average logic
    n = admin_metrics["total_claims"]
    prev_avg = admin_metrics["average_risk_score"]
    admin_metrics["average_risk_score"] = ((prev_avg * (n - 1)) + risk_score) / n

    # Notifications
    notify_user(request.user_id, f"Your claim resulted in: {decision.upper()}. Risk: {risk_score*100:.0f}%", decision)
    if payout:
        notify_user(request.user_id, "💸 Your lost wages have been credited instantly.", "success")
        
    notify_user("admin", f"New claim evaluated for {users[request.user_id]['name']}. Decision: {decision.upper()}, Risk Score: {risk_score*100:.0f}%", "alert" if risk_score > 0.5 else "info")

    return ClaimResponse(
        risk_score=risk_score,
        final_decision=decision,
        payout=payout
    )

@app.get("/api/notifications/{user}")
def get_notifications(user: str):
    user_lower = user.lower()
    if user_lower not in notifications:
        return []
    return notifications[user_lower]

@app.get("/api/admin/insights")
def get_admin_insights():
    return admin_metrics

@app.get("/api")
def read_root():
    return {"message": "Earn Protector API Running"}
