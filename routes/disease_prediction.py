import os
import tempfile
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from auth_utils import verify_token_dependency
from gradio_client import Client, handle_file
from database import history_collection
from datetime import datetime

load_dotenv()

router = APIRouter(prefix="/disease", tags=["Disease Detection"])
logger = logging.getLogger(__name__)

DISEASE_API_URL = os.getenv("DISEASE_API", "https://agrituni-plant-diseases-detection-classification.hf.space/")

# Lazy client
_disease_client = None

def get_disease_client():
    global _disease_client
    if _disease_client is None:
        try:
            _disease_client = Client(DISEASE_API_URL, token=os.getenv("HF_TOKEN"), verbose=False)
            print(f"✅ DISEASE client connected to {DISEASE_API_URL}")
        except Exception as e:
            print(f"❌ DISEASE client init error: {e}")
            _disease_client = False
    return _disease_client if _disease_client is not False else None 
    
@router.post("/predict")
async def predict_disease(file: UploadFile = File(...), current_user=Depends(verify_token_dependency)):
    client = get_disease_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Service de détection temporairement indisponible")

    # Use a temporary file (works on Render)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        content = await file.read()
        tmp.write(content)
        temp_path = tmp.name

    try:
        result = client.predict(img=handle_file(temp_path), api_name="/predict")
        # Parse result (same as before)
        predicted_class = "Unknown"
        confidence = 0.0
        if isinstance(result, dict):
            predicted_class = result.get("label", "Unknown")
            confidences = result.get("confidences", [])
            if confidences:
                confidence = confidences[0].get("confidence", 0.0)
        elif isinstance(result, (list, tuple)) and len(result) >= 2:
            predicted_class, confidence = result[0], float(result[1])
        else:
            predicted_class = str(result)

        # Save history
        await history_collection.insert_one({
    "user_email": current_user["email"],
    "operation_type": "disease_detection",
    "details": {"class": predicted_class, "confidence": confidence, "filename": file.filename},
    "status": "success",          # <--- AJOUTER CETTE LIGNE
    "created_at": datetime.utcnow()
})

        return {"class": predicted_class, "confidence": float(confidence)}
    except Exception as e:
        logger.exception("Gradio call failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)