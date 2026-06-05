from fastapi import APIRouter, HTTPException, Depends
from typing import List
from bson import ObjectId
from datetime import datetime
from database import notifications_collection, users_collection
from auth_utils import verify_token_dependency

router = APIRouter(prefix="/notifications", tags=["Notifications"])

def doc_to_id(doc):
    if "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

async def create_notification(user_email: str, type: str, title: str, message: str, icon: str, related_id: str = None):
    """Fonction utilitaire appelée par d’autres routes"""
    notif = {
        "user_email": user_email,
        "type": type,
        "title": title,
        "message": message,
        "icon": icon,
        "read": False,
        "created_at": datetime.utcnow(),
        "related_id": related_id
    }
    result = await notifications_collection.insert_one(notif)
    return str(result.inserted_id)

async def create_notification_for_admins(type: str, title: str, message: str, icon: str, related_id: str = None):
    """Crée une notification pour tous les administrateurs"""
    cursor = users_collection.find({"role": "admin"})
    admin_emails = []
    async for doc in cursor:
        admin_emails.append(doc["email"])
    
    for admin_email in admin_emails:
        notif = {
            "user_email": admin_email,
            "type": type,
            "title": title,
            "message": message,
            "icon": icon,
            "read": False,
            "created_at": datetime.utcnow(),
            "related_id": related_id
        }
        await notifications_collection.insert_one(notif)
    
    return len(admin_emails)

@router.get("/")
async def get_notifications(current_user=Depends(verify_token_dependency)):
    """Récupère les dernières notifications de l’utilisateur (max 50)"""
    cursor = notifications_collection.find({"user_email": current_user["email"]}).sort("created_at", -1).limit(50)
    items = []
    async for doc in cursor:
        items.append(doc_to_id(doc))
    return items

@router.get("/admin/unread-count")
async def get_admin_unread_count(current_user=Depends(verify_token_dependency)):
    """Récupère le nombre de notifications non lues pour l'admin"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    count = await notifications_collection.count_documents({
        "user_email": current_user["email"],
        "read": False
    })
    return {"unreadCount": count}

@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: str, current_user=Depends(verify_token_dependency)):
    try:
        obj_id = ObjectId(notification_id)
    except:
        raise HTTPException(400, "Invalid id")
    result = await notifications_collection.update_one(
        {"_id": obj_id, "user_email": current_user["email"]},
        {"$set": {"read": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Notification not found")
    return {"status": "success"}

@router.put("/read-all")
async def mark_all_as_read(current_user=Depends(verify_token_dependency)):
    await notifications_collection.update_many(
        {"user_email": current_user["email"], "read": False},
        {"$set": {"read": True}}
    )
    return {"status": "success"}