from fastapi import APIRouter, HTTPException, Depends
from typing import List
from bson import ObjectId
from database import diseases_collection
from models import DiseaseOut
from auth_utils import verify_token_dependency
from config import BASE_URL   # <-- import BASE_URL from config

router = APIRouter(prefix="/public/diseases", tags=["Public Diseases"])

def doc_to_id(doc):
    if "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

def fix_image_urls(doc):
    """Convert image filenames to absolute URLs using BASE_URL"""
    if "images" in doc and doc["images"]:
        fixed = []
        for img in doc["images"]:
            if img.startswith("http://") or img.startswith("https://"):
                fixed.append(img)
            elif img.startswith("/uploads/"):
                fixed.append(f"{BASE_URL}{img}")
            elif img.startswith("uploads/"):
                fixed.append(f"{BASE_URL}/{img}")
            else:
                # assume just filename
                fixed.append(f"{BASE_URL}/uploads/diseases/{img}")
        doc["images"] = fixed
    return doc

@router.get("/", response_model=List[DiseaseOut])
async def get_public_diseases(current_user=Depends(verify_token_dependency)):
    cursor = diseases_collection.find()
    diseases = []
    async for doc in cursor:
        doc = doc_to_id(doc)
        doc = fix_image_urls(doc)          # <-- fix URLs
        diseases.append(DiseaseOut(**doc))
    return diseases

@router.get("/{disease_id}", response_model=DiseaseOut)
async def get_public_disease_by_id(
    disease_id: str, 
    current_user=Depends(verify_token_dependency)
):
    try:
        obj_id = ObjectId(disease_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid disease id")
    
    disease = await diseases_collection.find_one({"_id": obj_id})
    if not disease:
        raise HTTPException(status_code=404, detail="Disease not found")
    
    disease = doc_to_id(disease)
    disease = fix_image_urls(disease)      # <-- fix URLs
    return DiseaseOut(**disease)