from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import List, Optional
from datetime import datetime, timedelta
from bson import ObjectId
from pydantic import BaseModel, Field
import os
import uuid
from pathlib import Path
import cloudinary
import cloudinary.uploader
import cloudinary.api
from database import users_collection, diseases_collection, topics_collection, farms_collection, history_collection
from auth_utils import verify_token_dependency
from config import CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, BASE_URL
from auth_utils import verify_token_dependency, hash_password

# Configuration Cloudinary
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)

router = APIRouter(prefix="/admin", tags=["Admin"])

# Configuration des uploads (garde la variable pour compatibilité, mais plus utilisée)
UPLOAD_DIR = Path("uploads/diseases")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# URL de base (gardée pour fallback)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Response models
class UserOut(BaseModel):
    id: str
    name: Optional[str] = None
    email: str
    role: Optional[str] = "agriculteur"  # ← peut être "admin" ou "agriculteur"
    status: Optional[str] = "actif"
    parcelles: Optional[int] = 0
    date: Optional[datetime] = None

class DiseaseOut(BaseModel):
    id: str
    name: str
    plants: List[str]
    severity: str
    symptoms: List[str]
    treatment: str
    prevention: Optional[str] = None
    images: Optional[List[str]] = None
    description: Optional[str] = None

class TopicOut(BaseModel):
    id: str
    title: str
    author: str
    date: datetime
    replies: int
    reports: Optional[int] = 0

class AdminStats(BaseModel):
    totalUsers: int
    newUsers: int
    totalParcelles: int
    totalArea: float
    totalTopics: int
    pendingTopics: int
    totalDiseases: int
    diseaseDetections: int

def doc_to_id(doc):
    """Convert MongoDB document _id to id and remove _id field"""
    if "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

# -------------------- Cloudinary functions (remplacent les fonctions locales) --------------------
def save_upload_file(upload_file: UploadFile) -> str:
    """Upload image to Cloudinary and return secure URL."""
    file_extension = Path(upload_file.filename).suffix.lower()
    if file_extension not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        raise HTTPException(status_code=400, detail="Format d'image non supporté")
    
    try:
        result = cloudinary.uploader.upload(
            upload_file.file,
            folder="agritunisie/diseases",
            use_filename=True,
            unique_filename=True
        )
        return result['secure_url']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Cloudinary: {str(e)}")

def delete_upload_file(image_url: str):
    """Delete image from Cloudinary using its URL."""
    try:
        if image_url and ('cloudinary' in image_url or image_url.startswith('http')):
            if '/upload/' in image_url:
                parts = image_url.split('/upload/')
                if len(parts) > 1:
                    public_id = parts[1].split('.')[0]
                    cloudinary.uploader.destroy(public_id)
    except Exception as e:
        print(f"Erreur suppression Cloudinary: {e}")

def get_image_url(identifier: str) -> str:
    """Return the image URL (already absolute from Cloudinary) or fallback for old images."""
    if identifier and (identifier.startswith('http://') or identifier.startswith('https://')):
        return identifier
    # Fallback pour les anciennes images locales
    return f"{BASE_URL}/uploads/diseases/{identifier}"

# -------------------- Upload d'image seule --------------------
@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...), current_user=Depends(verify_token_dependency)):
    """Upload a single image (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        url = save_upload_file(file)
        return {
            "status": "success",
            "url": url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- Upload multiple images --------------------
@router.post("/upload-images")
async def upload_multiple_images(
    files: List[UploadFile] = File(...),
    current_user=Depends(verify_token_dependency)
):
    """Upload multiple images (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        uploaded_files = []
        for file in files:
            url = save_upload_file(file)
            uploaded_files.append({
                "url": url
            })
        return {
            "status": "success",
            "files": uploaded_files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- Users --------------------
@router.get("/users", response_model=List[UserOut])
async def get_all_users(current_user=Depends(verify_token_dependency)):
    """Get all users (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        cursor = users_collection.find()
        users = []
        async for doc in cursor:
            doc = doc_to_id(doc)
            
            parcelles = await farms_collection.count_documents({"user_email": doc["email"]})
            
            name = doc.get("name") or doc.get("username")
            if not name:
                first = doc.get("firstName", "")
                last = doc.get("lastName", "")
                if first or last:
                    name = f"{first} {last}".strip()
                else:
                    name = doc["email"].split("@")[0]
            
            user = UserOut(
                id=doc["id"],
                name=name,
                email=doc["email"],
                role=doc.get("role", "agriculteur"),
                status=doc.get("status", "actif"),
                parcelles=parcelles,
                date=doc.get("created_at")
            )
            users.append(user)
        return users
    except Exception as e:
        print(f"Error in get_all_users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users", response_model=UserOut)
async def create_user(user_data: dict, current_user=Depends(verify_token_dependency)):
    """Create a new user (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    required = ["name", "email", "role", "status"]
    for field in required:
        if field not in user_data:
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")
    
    existing = await users_collection.find_one({"email": user_data["email"]})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # 🔧 Import des fonctions d'auth
    from auth_utils import hash_password
    
    # Préparer les données utilisateur
    name_parts = user_data["name"].split(" ", 1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    
    new_user = {
        "email": user_data["email"],
        "firstName": first_name,
        "lastName": last_name,
        "username": user_data["name"],
        "name": user_data["name"],
        "role": user_data.get("role", "agriculteur"),
        "status": user_data.get("status", "actif"),
        "provider": "email",
        "created_at": datetime.utcnow()
    }
    
    # Gestion du mot de passe
    password = user_data.get("password")
    if password and len(password) >= 6:
        new_user["password"] = hash_password(password)
        new_user["has_password"] = True
    else:
        new_user["password"] = None
        new_user["has_password"] = False
    
    result = await users_collection.insert_one(new_user)
    created = await users_collection.find_one({"_id": result.inserted_id})
    created = doc_to_id(created)
    created["parcelles"] = 0
    
    return UserOut(**created)

@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, user_data: dict, current_user=Depends(verify_token_dependency)):
    """Update a user (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid user id")
    
    # Vérifier que l'utilisateur existe
    existing_user = await users_collection.find_one({"_id": obj_id})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 🔧 Champs autorisés à la mise à jour
    update_fields = {}
    
    if "name" in user_data:
        update_fields["name"] = user_data["name"]
        update_fields["username"] = user_data["name"]
        # Mettre à jour firstName/lastName
        name_parts = user_data["name"].split(" ", 1)
        update_fields["firstName"] = name_parts[0] if name_parts else ""
        update_fields["lastName"] = name_parts[1] if len(name_parts) > 1 else ""
    
    if "role" in user_data:
        update_fields["role"] = user_data["role"]
    
    if "status" in user_data:
        update_fields["status"] = user_data["status"]
    
    # 🔧 Gestion du mot de passe (si fourni et non vide)
    if "password" in user_data and user_data["password"] and user_data["password"].strip():
        from auth_utils import hash_password
        if len(user_data["password"]) >= 6:
            update_fields["password"] = hash_password(user_data["password"])
            update_fields["has_password"] = True
        else:
            raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    result = await users_collection.update_one({"_id": obj_id}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    updated = await users_collection.find_one({"_id": obj_id})
    updated = doc_to_id(updated)
    
    parcelles = await farms_collection.count_documents({"user_email": updated["email"]})
    updated["parcelles"] = parcelles
    
    return UserOut(**updated)

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user=Depends(verify_token_dependency)):
    """Delete a user (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid user id")
    
    result = await users_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"status": "success"}

# -------------------- Diseases (avec Cloudinary) --------------------
@router.get("/diseases", response_model=List[DiseaseOut])
async def get_all_diseases(current_user=Depends(verify_token_dependency)):
    """Get all diseases (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    cursor = diseases_collection.find()
    diseases = []
    async for doc in cursor:
        doc = doc_to_id(doc)
        # Convertir les URLs (Cloudinary ou fallback local)
        if doc.get("images"):
            doc["images"] = [get_image_url(img) for img in doc["images"]]
        diseases.append(DiseaseOut(**doc))
    return diseases

@router.post("/diseases")
async def create_disease(
    name: str = Form(...),
    plant: str = Form(...),
    severity: str = Form(...),
    symptoms: str = Form(...),
    treatment: str = Form(...),
    prevention: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    images: List[UploadFile] = File(None),
    current_user=Depends(verify_token_dependency)
):
    """Create a new disease with image uploads (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Upload des images vers Cloudinary
        image_urls = []
        if images:
            for img in images:
                if img and img.filename:
                    url = save_upload_file(img)
                    image_urls.append(url)
        
        # Préparer les données
        plants_list = [p.strip() for p in plant.split(",") if p.strip()]
        symptoms_list = [s.strip() for s in symptoms.split("\n") if s.strip()]
        
        disease_data = {
            "name": name,
            "plants": plants_list,
            "severity": severity,
            "symptoms": symptoms_list,
            "treatment": treatment,
            "prevention": prevention,
            "description": description,
            "images": image_urls,
            "created_at": datetime.utcnow()
        }
        
        result = await diseases_collection.insert_one(disease_data)
        created = await diseases_collection.find_one({"_id": result.inserted_id})
        created = doc_to_id(created)
        
        # Retourner avec URLs complètes
        if created.get("images"):
            created["images"] = [get_image_url(img) for img in created["images"]]
        
        return DiseaseOut(**created)
        
    except Exception as e:
        print(f"Error creating disease: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/diseases/{disease_id}")
async def update_disease(
    disease_id: str,
    name: Optional[str] = Form(None),
    plant: Optional[str] = Form(None),
    severity: Optional[str] = Form(None),
    symptoms: Optional[str] = Form(None),
    treatment: Optional[str] = Form(None),
    prevention: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    existing_images: Optional[str] = Form(None),  # JSON string of existing image URLs
    images: List[UploadFile] = File(None),
    current_user=Depends(verify_token_dependency)
):
    """Update a disease with image uploads (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        obj_id = ObjectId(disease_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid disease id")
    
    # Récupérer la maladie existante
    existing_disease = await diseases_collection.find_one({"_id": obj_id})
    if not existing_disease:
        raise HTTPException(status_code=404, detail="Disease not found")
    
    # Préparer les URLs des images
    image_urls = []
    
    # Garder les images existantes
    if existing_images:
        import json
        try:
            image_urls = json.loads(existing_images)
        except:
            pass
    
    # Ajouter les nouvelles images (upload vers Cloudinary)
    if images:
        for img in images:
            if img and img.filename:
                url = save_upload_file(img)
                image_urls.append(url)
    
    # Préparer les données de mise à jour
    update_data = {}
    
    if name is not None:
        update_data["name"] = name
    if plant is not None:
        plants_list = [p.strip() for p in plant.split(",") if p.strip()]
        update_data["plants"] = plants_list
    if severity is not None:
        update_data["severity"] = severity
    if symptoms is not None:
        symptoms_list = [s.strip() for s in symptoms.split("\n") if s.strip()]
        update_data["symptoms"] = symptoms_list
    if treatment is not None:
        update_data["treatment"] = treatment
    if prevention is not None:
        update_data["prevention"] = prevention
    if description is not None:
        update_data["description"] = description
    if image_urls:
        update_data["images"] = image_urls
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    result = await diseases_collection.update_one({"_id": obj_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Disease not found")
    
    updated = await diseases_collection.find_one({"_id": obj_id})
    updated = doc_to_id(updated)
    
    # Retourner avec URLs complètes
    if updated.get("images"):
        updated["images"] = [get_image_url(img) for img in updated["images"]]
    
    return DiseaseOut(**updated)

@router.delete("/diseases/{disease_id}")
async def delete_disease(disease_id: str, current_user=Depends(verify_token_dependency)):
    """Delete a disease and its images from Cloudinary (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        obj_id = ObjectId(disease_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid disease id")
    
    # Récupérer la maladie pour supprimer les images
    disease = await diseases_collection.find_one({"_id": obj_id})
    if not disease:
        raise HTTPException(status_code=404, detail="Disease not found")
    
    # Supprimer les images de Cloudinary
    if disease.get("images"):
        for img_url in disease["images"]:
            delete_upload_file(img_url)
    
    result = await diseases_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Disease not found")
    
    return {"status": "success"}

# -------------------- Forum Topics --------------------
@router.get("/topics/reported", response_model=List[TopicOut])
async def get_reported_topics(current_user=Depends(verify_token_dependency)):
    """Get reported topics (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    cursor = topics_collection.find({"reports": {"$gt": 0}}).sort("date", -1)
    topics = []
    async for doc in cursor:
        doc = doc_to_id(doc)
        topics.append(TopicOut(**doc))
    return topics

@router.get("/topics/recent", response_model=List[TopicOut])
async def get_recent_topics(current_user=Depends(verify_token_dependency)):
    """Get recent topics (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    cursor = topics_collection.find().sort("date", -1).limit(10)
    topics = []
    async for doc in cursor:
        doc = doc_to_id(doc)
        topics.append(TopicOut(**doc))
    return topics

@router.get("/topics/pending", response_model=List[TopicOut])
async def get_pending_topics(current_user=Depends(verify_token_dependency)):
    """Get topics pending moderation (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    cursor = topics_collection.find({"status": "pending"}).sort("date", -1)
    topics = []
    async for doc in cursor:
        doc = doc_to_id(doc)
        # Ajouter un excerpt pour l'affichage
        doc["excerpt"] = doc.get("content", "")[:100] + "..."
        topics.append(TopicOut(**doc))
    return topics

@router.put("/topics/{topic_id}/approve")
async def approve_topic(topic_id: str, current_user=Depends(verify_token_dependency)):
    """Approve a reported topic (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid topic id")
    
    result = await topics_collection.update_one(
        {"_id": obj_id}, 
        {"$set": {"reports": 0, "status": "approved"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    return {"status": "success"}

@router.put("/topics/{topic_id}/approve-forum")
async def approve_forum_topic(topic_id: str, current_user=Depends(verify_token_dependency)):
    """Approve a pending forum topic (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid topic id")
    
    result = await topics_collection.update_one(
        {"_id": obj_id}, 
        {"$set": {"status": "approved"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    return {"status": "success"}

@router.put("/topics/{topic_id}/reject")
async def reject_forum_topic(topic_id: str, current_user=Depends(verify_token_dependency)):
    """Reject a pending forum topic (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid topic id")
    
    result = await topics_collection.update_one(
        {"_id": obj_id}, 
        {"$set": {"status": "rejected"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    return {"status": "success"}

@router.delete("/topics/{topic_id}")
async def delete_topic(topic_id: str, current_user=Depends(verify_token_dependency)):
    """Delete a topic (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid topic id")
    
    result = await topics_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    return {"status": "success"}

@router.delete("/topics/{topic_id}/forum")
async def delete_forum_topic(topic_id: str, current_user=Depends(verify_token_dependency)):
    """Delete a forum topic (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        obj_id = ObjectId(topic_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid topic id")
    
    result = await topics_collection.delete_one({"_id": obj_id})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    return {"status": "success"}

# -------------------- Statistics --------------------
@router.get("/stats", response_model=AdminStats)
async def get_stats(current_user=Depends(verify_token_dependency)):
    """Get admin statistics (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    total_users = await users_collection.count_documents({})
    
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_users = await users_collection.count_documents({"created_at": {"$gte": thirty_days_ago}})
    
    total_parcelles = 0
    async for farm in farms_collection.find():
        total_parcelles += len(farm.get("parcels", []))
    
    total_area = 0
    async for farm in farms_collection.find():
        for parcel in farm.get("parcels", []):
            total_area += parcel.get("area", 0)
    
    total_topics = await topics_collection.count_documents({})
    pending_topics = await topics_collection.count_documents({"reports": {"$gt": 0}})
    
    total_diseases = await diseases_collection.count_documents({})
    
    disease_detections = await history_collection.count_documents({"operation_type": "disease_detection"})
    
    return AdminStats(
        totalUsers=total_users,
        newUsers=new_users,
        totalParcelles=total_parcelles,
        totalArea=total_area,
        totalTopics=total_topics,
        pendingTopics=pending_topics,
        totalDiseases=total_diseases,
        diseaseDetections=disease_detections
    )