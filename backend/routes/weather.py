from fastapi import APIRouter
from services.db import now_iso
from services.logic import get_weather, evaluate_triggers
router = APIRouter()

@router.get("/{city}")
async def weather(city:str):
    w = await get_weather(city)
    t = evaluate_triggers(w["rain_mm"],w["temp_c"],w["aqi"])
    return {**w,"city":city,"triggers":t,"fetched_at":now_iso()}
