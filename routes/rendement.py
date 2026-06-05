import os
from dotenv import load_dotenv
from gradio_client import Client
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from auth_utils import verify_token_dependency
from database import history_collection  # ← seule collection utilisée
import re

load_dotenv()
router = APIRouter(prefix="/rendement", tags=["Rendement"])

HF_TOKEN = os.getenv("HF_TOKEN")
SPACE_ID = os.getenv("RENDEMENT_SPACE_ID", "AgriTuni/prediction_de_rendement")
os.environ["HF_TOKEN"] = HF_TOKEN or ""

# Lazy client
_rendement_client = None

def get_rendement_client():
    global _rendement_client
    if _rendement_client is None:
        try:
            _rendement_client = Client(SPACE_ID)
            print(f"✅ RENDEMENT client connected to {SPACE_ID}")
        except Exception as e:
            print(f"❌ RENDEMENT client init error: {e}")
            _rendement_client = False
    return _rendement_client if _rendement_client is not False else None

class PredictionRequest(BaseModel):
    region: str
    soil_type: str
    crop: str
    rainfall: float
    temperature: float
    fertilizer_used: bool
    irrigation_used: str
    weather_condition: str
    days_to_harvest: int

@router.post("/predict")
async def predict_rendement(request: PredictionRequest, current_user=Depends(verify_token_dependency)):
    client = get_rendement_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Service de prédiction temporairement indisponible. Réessayez plus tard.")
    try:
        result = client.predict(
            request.region,
            request.soil_type,
            request.crop,
            request.rainfall,
            request.temperature,
            request.fertilizer_used,
            request.irrigation_used,
            request.weather_condition,
            request.days_to_harvest,
            api_name="/predict"
        )
        match = re.search(r"(\d+\.?\d*)", str(result))
        if match:
            yield_tonnes = float(match.group(1))
            # 🔹 Stocker dans history_collection UNIQUEMENT
            await history_collection.insert_one({
                "user_email": current_user["email"],
                "operation_type": "yield_prediction",
                "operation_key": "HISTORY.OPERATION.YIELD_PREDICTION",  # clé de traduction
                "details": {
                    "yield": yield_tonnes,
                    "crop": request.crop,
                    "soil_type": request.soil_type,
                    "rainfall": request.rainfall,
                    "temperature": request.temperature,
                    "fertilizer_used": request.fertilizer_used,
                    "irrigation_used": request.irrigation_used,
                    "weather_condition": request.weather_condition,
                    "days_to_harvest": request.days_to_harvest
                },
                "status": "success",
                "created_at": datetime.utcnow()
            })
            return {"yield_tonnes_per_ha": yield_tonnes, "raw_response": str(result)}
        else:
            raise HTTPException(status_code=500, detail="Format de réponse inattendu")
    except Exception as e:
        print(f"❌ API call error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{user_email}")
async def get_yield_history(user_email: str, limit: int = 5):
    # On filtre les entrées de type yield_prediction dans history
    cursor = history_collection.find({
        "user_email": user_email,
        "operation_type": "yield_prediction"
    }).sort("created_at", -1).limit(limit)
    history = await cursor.to_list(length=limit)
    for doc in history:
        doc["_id"] = str(doc["_id"])
    return history