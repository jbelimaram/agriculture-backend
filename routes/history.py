from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from bson import ObjectId
from models import HistoryEntry
from database import history_collection
# from auth import get_current_user  # À décommenter quand l'authentification sera prête

router = APIRouter(prefix="/api/history", tags=["History"])

@router.post("/")
async def add_history(entry: HistoryEntry):
    entry_dict = entry.dict()
    entry_dict["created_at"] = datetime.utcnow()
    await history_collection.insert_one(entry_dict)
    return {"status": "success", "message": "Historique enregistré"}

@router.get("/{user_email}")
async def get_history(user_email: str, limit: int = 100, skip: int = 0):
    cursor = history_collection.find({"user_email": user_email}).sort("created_at", -1).skip(skip).limit(limit)
    entries = await cursor.to_list(length=limit)
    total = await history_collection.count_documents({"user_email": user_email})
    for e in entries:
        e["_id"] = str(e["_id"])
    return {"entries": entries, "total": total}

# Supprimer une entrée spécifique
@router.delete("/{user_email}/{entry_id}")
async def delete_history_entry(
    user_email: str,
    entry_id: str,
    # current_user = Depends(get_current_user)   # Décommenter avec l'auth
):
    # Vérification d'authentification à activer plus tard
    # if current_user["email"] != user_email:
    #     raise HTTPException(status_code=403, detail="Non autorisé")
    
    result = await history_collection.delete_one({"_id": ObjectId(entry_id), "user_email": user_email})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entrée non trouvée")
    return {"status": "success", "message": "Entrée supprimée"}

# Supprimer tout l'historique d'un utilisateur
@router.delete("/{user_email}")
async def clear_all_history(
    user_email: str,
    # current_user = Depends(get_current_user)
):
    # if current_user["email"] != user_email:
    #     raise HTTPException(status_code=403, detail="Non autorisé")
    
    result = await history_collection.delete_many({"user_email": user_email})
    return {"status": "success", "message": f"{result.deleted_count} entrées supprimées"}