import os
from dotenv import load_dotenv
from gradio_client import Client
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Optional
import httpx
import re
from routes.notifications import create_notification
from models import SensorData
from database import sensor_data_collection, db

load_dotenv()

router = APIRouter(prefix="/api/sensors", tags=["Sensors"])

# ========== TABLE FAO ==========
FAO_DURATIONS = {
    "tomate": {"clay": [6,8], "sandy": [10,14], "tourbeux": [5,7], "limoneux": [7,10]},
    "olivier": {"clay": [8,12], "sandy": [12,20], "tourbeux": [7,10], "limoneux": [9,14]},
    "pomme_de_terre": {"clay": [7,9], "sandy": [12,15], "tourbeux": [6,8], "limoneux": [8,11]},
    "epinard": {"clay": [4,6], "sandy": [8,10], "tourbeux": [4,5], "limoneux": [5,7]},
    "salade": {"clay": [5,7], "sandy": [9,12], "tourbeux": [5,6], "limoneux": [6,8]}
}

# ========== HUGGING FACE ==========
HF_TOKEN = os.getenv("HF_TOKEN")
SPACE_URL = os.getenv("IRRIGATION_API", "https://agrituni-irrigation-system.hf.space/")
os.environ["HF_TOKEN"] = HF_TOKEN or ""
try:
    client = Client(SPACE_URL)
    print("✅ Client Hugging Face initialisé")
except Exception as e:
    print(f"❌ Erreur initialisation client HF: {e}")
    client = None

# ========== MÉTÉO ==========
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "d1a7be5bf70dc46506622a85d589d2f6")

async def get_rain_probability(lat: float, lon: float) -> Optional[float]:
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric", "cnt": 4}
    try:
        async with httpx.AsyncClient() as client_http:
            resp = await client_http.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                max_pop = 0.0
                for item in data.get("list", []):
                    pop = item.get("pop", 0.0)
                    max_pop = max(max_pop, pop * 100)
                return max_pop
    except Exception as e:
        print(f"⚠️ Erreur météo: {e}")
    return None

# ========== FONCTIONS ==========
async def get_parcelle_info(user_email: str, parcelle_id: str):
    farm = await db["farms"].find_one({"user_email": user_email})
    if not farm:
        return None, None, None, None
    for p in farm.get("parcels", []):
        if p.get("id") == parcelle_id:
            return p.get("crop"), p.get("soilType"), farm.get("latitude"), farm.get("longitude")
    return None, None, None, None

def get_irrigation_duration(crop: str, soil: str) -> int:
    crop_key = crop.lower().replace(" ", "_")
    soil_key = soil.lower()
    durations = FAO_DURATIONS.get(crop_key, {}).get(soil_key)
    return (durations[0] + durations[1]) // 2 if durations else 5

# ========== ROUTE PRINCIPALE ==========
@router.post("/data")
async def receive_sensor_data(data: SensorData):
    if not data.parcelle_id:
        raise HTTPException(400, detail="parcelle_id requis")

    crop, soil, lat, lon = await get_parcelle_info(data.user_email, data.parcelle_id)
    if not crop or not soil:
        raise HTTPException(404, detail="Parcelle non trouvée")

    rain_prob = await get_rain_probability(lat, lon) if lat and lon else None

    decision_ia = False
    ai_confidence = 0.0
    irrigation_minutes = 0

    # Si pluie > 70% → OFF direct
    if rain_prob is not None and rain_prob > 70.0:
        decision_ia = False
        ai_confidence = 100.0
        irrigation_minutes = 0
        await create_notification(
            user_email=data.user_email, type="irrigation_cancelled",
            title="⛈️ Irrigation annulée",
            message=f"Probabilité de pluie de {rain_prob:.1f}% dans les 12h. L'irrigation a été annulée.",
            icon="fa-cloud-rain"
        )
    else:
        # Appel IA
        if client:
            try:
                result = client.predict(
                    soil=data.soil_moisture, temp=data.temperature,
                    humidity=data.air_humidity, api_name="/predict_pump"
                )
                decision_ia = "ON" in result
                match = re.search(r"\((\d+\.?\d*)%\)", result)
                ai_confidence = float(match.group(1)) if match else (99.0 if decision_ia else 1.0)
                print(f"🤖 {result} → {'ON' if decision_ia else 'OFF'} (conf: {ai_confidence}%)")
            except Exception as e:
                print(f"⚠️ IA: {e}")
        # Durée FAO si ON
        if decision_ia:
            irrigation_minutes = get_irrigation_duration(crop, soil)
            print(f"💧 FAO: {irrigation_minutes} min")

    # Sauvegarde
    record = data.dict()
    record["timestamp"] = datetime.utcnow()
    record["irrigation_decision"] = decision_ia
    record["irrigation_duration"] = irrigation_minutes
    record["ai_confidence"] = ai_confidence
    await sensor_data_collection.insert_one(record)

    # Notifications de seuils
    if data.temperature > 35:
        await create_notification(
            user_email=data.user_email, type="alert_temp_high",
            title="🌡️ Température élevée",
            message=f"Température de {data.temperature}°C détectée. Risque pour les cultures.",
            icon="fa-temperature-high"
        )
    elif data.temperature < 5:
        await create_notification(
            user_email=data.user_email, type="alert_temp_low",
            title="❄️ Risque de gel",
            message=f"Température de {data.temperature}°C. Protégez vos cultures.",
            icon="fa-snowflake"
        )
    if data.air_humidity < 30:
        await create_notification(
            user_email=data.user_email, type="alert_humidity_low",
            title="💧 Humidité de l'air faible",
            message=f"Humidité de l'air à {data.air_humidity}%. Risque de stress hydrique.",
            icon="fa-tint"
        )
    if data.soil_moisture < 25:
        await create_notification(
            user_email=data.user_email, type="alert_soil_dry",
            title="🌱 Sol trop sec",
            message=f"Humidité du sol à {data.soil_moisture}%. Arrosage recommandé.",
            icon="fa-seedling"
        )

    return {
        "status": "success",
        "pump_state": "ON" if decision_ia else "OFF",
        "duration_minutes": irrigation_minutes,
        "crop": crop,
        "soil": soil,
        "light_intensity": data.light_intensity,
        "confidence": ai_confidence
    }

# ========== ROUTES LATEST & HISTORY (inchangées) ==========
@router.get("/latest/{user_email}")
async def get_latest_data(user_email: str, parcelle_id: Optional[str] = None):
    query = {"user_email": user_email}
    if parcelle_id:
        query["parcelle_id"] = parcelle_id
    cursor = sensor_data_collection.find(query).sort("timestamp", -1).limit(1)
    latest = await cursor.to_list(length=1)
    if latest:
        latest[0]["_id"] = str(latest[0]["_id"])
        if "light_intensity" not in latest[0]:
            latest[0]["light_intensity"] = None
        if "ai_confidence" not in latest[0]:
            latest[0]["ai_confidence"] = 80.0
        return latest[0]
    return {"message": "No data"}

@router.get("/history/{user_email}")
async def get_sensor_history(user_email: str, parcelle_id: Optional[str] = None, limit: int = 100):
    query = {"user_email": user_email}
    if parcelle_id:
        query["parcelle_id"] = parcelle_id
    cursor = sensor_data_collection.find(query).sort("timestamp", -1).limit(limit)
    history = await cursor.to_list(length=limit)
    for record in history:
        record["_id"] = str(record["_id"])
        if "light_intensity" not in record:
            record["light_intensity"] = None
        if "ai_confidence" not in record:
            record["ai_confidence"] = 80.0
    return history