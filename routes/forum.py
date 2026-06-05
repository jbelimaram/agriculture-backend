# routes/forum.py
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
from database import topics_collection, replies_collection, users_collection
from routes.notifications import create_notification, create_notification_for_admins
from auth_utils import verify_token_dependency
from models import Topic, Reply
import uuid
import cloudinary
import cloudinary.uploader
import cloudinary.api
from config import CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET

# Configuration Cloudinary (déjà faite dans admin.py, mais on la répète par sécurité)
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)

router = APIRouter(prefix="/forum", tags=["Forum"])

def doc_to_id(doc):
    if "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

# ---------- Upload image vers Cloudinary ----------
@router.post("/upload")
async def upload_image(file: UploadFile = File(...), current_user=Depends(verify_token_dependency)):
    if not file.content_type.startswith('image/'):
        raise HTTPException(400, "File must be an image")
    try:
        # Upload vers Cloudinary dans un dossier "forum"
        result = cloudinary.uploader.upload(
            file.file,
            folder="agritunisie/forum",
            use_filename=True,
            unique_filename=True
        )
        return {"url": result['secure_url']}
    except Exception as e:
        raise HTTPException(500, f"Erreur Cloudinary: {str(e)}")

# ---------- Topics (public) ----------
@router.get("/topics", response_model=List[dict])
async def get_topics(
    category: Optional[str] = None, 
    sort_by: str = "recent", 
    current_user=Depends(verify_token_dependency)
):
    query = {"status": "approved"}
    if category and category != "all":
        query["category"] = category
    cursor = topics_collection.find(query)
    topics = []
    async for doc in cursor:
        doc = doc_to_id(doc)
        # Les images sont déjà des URLs Cloudinary (ou des chemins locaux anciens)
        # On les laisse telles quelles
        topics.append(doc)
    if sort_by == "recent":
        topics.sort(key=lambda t: t.get("date", datetime.min), reverse=True)
    elif sort_by == "popular":
        topics.sort(key=lambda t: t.get("views", 0), reverse=True)
    elif sort_by == "unsolved":
        topics = [t for t in topics if not t.get("solved", False)]
    return topics

@router.get("/admin/topics", response_model=List[dict])
async def get_all_topics_admin(
    status: Optional[str] = None,
    current_user=Depends(verify_token_dependency)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    query = {}
    if status and status != "all":
        query["status"] = status
    cursor = topics_collection.find(query).sort("date", -1)
    topics = []
    async for doc in cursor:
        doc = doc_to_id(doc)
        topics.append(doc)
    return topics

@router.get("/my-topics", response_model=List[dict])
async def get_my_topics(current_user=Depends(verify_token_dependency)):
    cursor = topics_collection.find({"author_email": current_user["email"]}).sort("date", -1)
    topics = []
    async for doc in cursor:
        doc = doc_to_id(doc)
        topics.append(doc)
    return topics

# ---------- Create topic ----------
@router.post("/topics", response_model=dict)
async def create_topic(topic_data: dict, current_user=Depends(verify_token_dependency)):
    required = ["title", "category", "fullContent"]
    for field in required:
        if field not in topic_data:
            raise HTTPException(400, f"Missing field: {field}")
    user = await users_collection.find_one({"email": current_user["email"]})
    author_name = user.get("name") or user.get("username") or current_user["email"].split("@")[0]
    excerpt = topic_data["fullContent"][:100] + ("..." if len(topic_data["fullContent"]) > 100 else "")
    new_topic = {
        "title": topic_data["title"],
        "excerpt": excerpt,
        "fullContent": topic_data["fullContent"],
        "category": topic_data["category"],
        "author": author_name,
        "author_email": current_user["email"],
        "replies": 0,
        "views": 0,
        "solved": False,
        "status": "pending",
        "reports": 0,
        "date": datetime.utcnow(),
        "images": topic_data.get("images", [])   # déjà des URLs Cloudinary
    }
    result = await topics_collection.insert_one(new_topic)
    created = await topics_collection.find_one({"_id": result.inserted_id})
    created = doc_to_id(created)
    return created

# ---------- Admin approve / reject ----------
@router.put("/admin/topics/{topic_id}/approve")
async def approve_topic(topic_id: str, current_user=Depends(verify_token_dependency)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(400, "Invalid id")
    result = await topics_collection.update_one({"_id": obj_id}, {"$set": {"status": "approved"}})
    if result.matched_count == 0:
        raise HTTPException(404, "Topic not found")
    topic = await topics_collection.find_one({"_id": obj_id})
    if topic:
        await create_notification(
            user_email=topic["author_email"],
            type="forum_approved",
            title="✅ Sujet approuvé",
            message=f"Votre sujet « {topic['title']} » a été approuvé et est maintenant visible.",
            icon="fa-check-circle",
            related_id=topic_id
        )
    return {"status": "success", "message": "Topic approved"}

@router.put("/admin/topics/{topic_id}/reject")
async def reject_topic(topic_id: str, current_user=Depends(verify_token_dependency)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(400, "Invalid id")
    result = await topics_collection.update_one({"_id": obj_id}, {"$set": {"status": "rejected"}})
    if result.matched_count == 0:
        raise HTTPException(404, "Topic not found")
    topic = await topics_collection.find_one({"_id": obj_id})
    if topic:
        await create_notification(
            user_email=topic["author_email"],
            type="forum_rejected",
            title="❌ Sujet rejeté",
            message=f"Votre sujet « {topic['title']} » a été rejeté par l'administrateur.",
            icon="fa-times-circle",
            related_id=topic_id
        )
    return {"status": "success", "message": "Topic rejected"}

@router.delete("/admin/topics/{topic_id}")
async def delete_topic_admin(topic_id: str, current_user=Depends(verify_token_dependency)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(400, "Invalid id")
    result = await topics_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Topic not found")
    return {"status": "success"}

# ---------- Get single topic ----------
@router.get("/topics/{topic_id}", response_model=dict)
async def get_topic(topic_id: str, current_user=Depends(verify_token_dependency)):
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(400, "Invalid id")
    topic = await topics_collection.find_one({"_id": obj_id})
    if not topic:
        raise HTTPException(404, "Topic not found")
    if topic.get("status") == "approved":
        user = await users_collection.find_one({"email": current_user["email"]})
        if user:
            viewed_topics = user.get("viewed_topics", [])
            if topic_id not in viewed_topics:
                await topics_collection.update_one({"_id": obj_id}, {"$inc": {"views": 1}})
                await users_collection.update_one(
                    {"email": current_user["email"]},
                    {"$push": {"viewed_topics": topic_id}}
                )
    topic = doc_to_id(topic)
    return topic

# ---------- Replies ----------
@router.get("/replies/{topic_id}", response_model=List[dict])
async def get_replies(topic_id: str, current_user=Depends(verify_token_dependency)):
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(400, "Invalid id")
    cursor = replies_collection.find({"topicId": topic_id}).sort("date", 1)
    replies = []
    async for doc in cursor:
        doc = doc_to_id(doc)
        replies.append(doc)
    return replies

@router.post("/replies", response_model=dict)
async def add_reply(reply_data: dict, current_user=Depends(verify_token_dependency)):
    required = ["topicId", "content"]
    for field in required:
        if field not in reply_data:
            raise HTTPException(400, f"Missing field: {field}")
    try:
        topic_id = ObjectId(reply_data["topicId"])
    except:
        raise HTTPException(400, "Invalid topicId")
    topic = await topics_collection.find_one({"_id": topic_id})
    if not topic:
        raise HTTPException(404, "Topic not found")
    if topic.get("status") != "approved":
        raise HTTPException(403, "Cannot reply to non-approved topic")
    user = await users_collection.find_one({"email": current_user["email"]})
    author_name = user.get("name") or user.get("username") or current_user["email"].split("@")[0]
    new_reply = {
        "topicId": reply_data["topicId"],
        "author": author_name,
        "author_email": current_user["email"],
        "content": reply_data["content"],
        "date": datetime.utcnow(),
        "helpfulCount": 0,
        "images": reply_data.get("images", [])   # déjà des URLs Cloudinary
    }
    result = await replies_collection.insert_one(new_reply)
    await topics_collection.update_one({"_id": topic_id}, {"$inc": {"replies": 1}})
    created = await replies_collection.find_one({"_id": result.inserted_id})
    created = doc_to_id(created)

    if topic["author_email"] != current_user["email"]:
        await create_notification(
            user_email=topic["author_email"],
            type="forum_reply",
            title="💬 Nouvelle réponse",
            message=f"{author_name} a répondu à votre sujet « {topic['title']} ».",
            icon="fa-comment",
            related_id=reply_data["topicId"]
        )
    return created

# ---------- Mark reply as helpful ----------
@router.put("/replies/{reply_id}/helpful")
async def mark_helpful(reply_id: str, current_user=Depends(verify_token_dependency)):
    try:
        obj_id = ObjectId(reply_id)
    except:
        raise HTTPException(400, "Invalid id")
    
    reply = await replies_collection.find_one({"_id": obj_id})
    if not reply:
        raise HTTPException(404, "Reply not found")
    
    if reply.get("author_email") == current_user["email"]:
        raise HTTPException(400, "You cannot mark your own reply as helpful")
    
    helpful_users = reply.get("helpful_users", [])
    if current_user["email"] in helpful_users:
        raise HTTPException(400, "You have already marked this reply as helpful")
    
    await replies_collection.update_one(
        {"_id": obj_id}, 
        {
            "$inc": {"helpfulCount": 1},
            "$push": {"helpful_users": current_user["email"]}
        }
    )
    
    topic = await topics_collection.find_one({"_id": ObjectId(reply["topicId"])}) if reply.get("topicId") else None
    topic_title = topic.get("title", "un sujet") if topic else "un sujet"
    
    user = await users_collection.find_one({"email": current_user["email"]})
    user_name = user.get("name") or user.get("username") or current_user["email"].split("@")[0]
    
    if reply["author_email"] != current_user["email"]:
        await create_notification(
            user_email=reply["author_email"],
            type="reply_helpful",
            title="👍 Votre réponse a été appréciée",
            message=f"{user_name} a trouvé votre réponse utile sur le sujet « {topic_title} ».",
            icon="fa-thumbs-up",
            related_id=reply_id
        )
    
    return {"status": "success", "helpfulCount": reply.get("helpfulCount", 0) + 1}

# ---------- Report topic ----------
@router.post("/topics/{topic_id}/report")
async def report_topic(
    topic_id: str, 
    current_user=Depends(verify_token_dependency)
):
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid topic id")
    
    topic = await topics_collection.find_one({"_id": obj_id})
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    if topic.get("author_email") == current_user["email"]:
        raise HTTPException(status_code=400, detail="You cannot report your own topic")
    
    await topics_collection.update_one(
        {"_id": obj_id},
        {"$inc": {"reports": 1}}
    )
    
    updated_topic = await topics_collection.find_one({"_id": obj_id})
    reports_count = updated_topic.get("reports", 1)
    
    title = f"⚠️ Sujet signalé : {topic.get('title', 'Sans titre')}"
    message = f"Le sujet '{topic.get('title', 'Sans titre')}' a été signalé par {current_user['email']}. Total signalements : {reports_count}"
    
    await create_notification_for_admins(
        type="topic_report",
        title=title,
        message=message,
        icon="fa-flag",
        related_id=topic_id
    )
    
    return {
        "status": "success", 
        "message": "Topic reported successfully",
        "reports": reports_count
    }

# ---------- Delete own topic ----------
@router.delete("/topics/{topic_id}")
async def delete_my_topic(topic_id: str, current_user=Depends(verify_token_dependency)):
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(400, "Invalid topic id")
    topic = await topics_collection.find_one({"_id": obj_id})
    if not topic:
        raise HTTPException(404, "Topic not found")
    if topic.get("author_email") != current_user["email"]:
        raise HTTPException(403, "You can only delete your own topics")
    await replies_collection.delete_many({"topicId": topic_id})
    result = await topics_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Topic not found")
    return {"status": "success", "message": "Topic deleted"}