from fastapi import APIRouter, HTTPException
from models import FarmSetup
from database import farms_collection

router = APIRouter(prefix="/farm", tags=["Farm"])

@router.post("/save")
async def save_farm(farm: FarmSetup):
    await farms_collection.update_one(
        {"user_email": farm.user_email},
        {"$set": farm.dict()},
        upsert=True
    )
    return {"status": "success", "message": "Configuration enregistrée"}

@router.get("/{user_email}")
async def get_farm(user_email: str):
    farm = await farms_collection.find_one({"user_email": user_email})
    if not farm:
        raise HTTPException(status_code=404, detail="Ferme non trouvée")
    if "_id" in farm:
        farm["_id"] = str(farm["_id"])
    return farm