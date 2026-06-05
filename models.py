from pydantic import BaseModel, EmailStr, validator  # ⭐ AJOUTER validator
from typing import List, Optional
from datetime import datetime
import os

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
# ----- Auth models -----
class UserRegister(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    phone: str
    password: str

class SetPasswordRequest(BaseModel):
    password: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordConfirm(BaseModel):
    token: str
    new_password: str

# ----- Farm models -----
class Parcel(BaseModel):
    id: str
    name: str
    area: float
    soilType: str
    crop: str

class FarmSetup(BaseModel):
    user_email: EmailStr
    name: str
    size: float
    region: str
    parcels: List[Parcel]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None

# ----- Sensor models -----
class SensorData(BaseModel):
    user_email: EmailStr
    temperature: float
    air_humidity: float
    soil_moisture: float
    light_intensity: float
    parcelle_id: Optional[str] = None


# ----- History models -----
class HistoryEntry(BaseModel):
    user_email: EmailStr
    operation_type: str
    operation_key: str
    details: dict
    status: str
    created_at: datetime = datetime.utcnow()

# ----- Admin models -----
class UserOut(BaseModel):
    id: str
    name: Optional[str] = None
    email: str
    role: Optional[str] = "agriculteur"
    status: Optional[str] = "actif"
    parcelles: Optional[int] = 0
    date: Optional[datetime] = None

# ----- Topic and Reply models -----
class Topic(BaseModel):
    id: Optional[str] = None
    title: str
    excerpt: str
    fullContent: str
    category: str
    author: str
    author_email: EmailStr
    replies: int = 0
    views: int = 0
    solved: bool = False
    status: str = "pending"
    date: datetime = datetime.utcnow()
    images: Optional[List[dict]] = []

class Reply(BaseModel):
    id: Optional[str] = None
    topicId: str
    author: str
    author_email: EmailStr
    content: str
    date: datetime = datetime.utcnow()
    helpfulCount: int = 0
    helpful_users: List[str] = []

# ----- DiseaseOut model with image URL fix -----
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
    
    @staticmethod
    def get_image_url(filename: str) -> str:
        """Convertit un nom de fichier en URL complète"""
        BASE_URL = "http://localhost:8000"
        if not filename:
            return ""
        if filename.startswith("http://") or filename.startswith("https://"):
            return filename
        if filename.startswith("/uploads/"):
            return f"{BASE_URL}{filename}"
        if not filename.startswith("uploads/") and "/" not in filename:
            return f"{BASE_URL}/uploads/diseases/{filename}"
        if filename.startswith("uploads/"):
            return f"{BASE_URL}/{filename}"
        return filename
    
    @validator('images', pre=True, always=True)
    def fix_images(cls, v):
        if v:
            return [cls.get_image_url(img) for img in v]
        return []

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

class Notification(BaseModel):
    id: Optional[str] = None
    user_email: EmailStr
    type: str
    title: str
    message: str
    icon: str
    read: bool = False
    created_at: datetime = datetime.utcnow()
    related_id: Optional[str] = None