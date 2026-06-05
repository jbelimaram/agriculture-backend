from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)
db = client["agritunisie"]

users_collection = db["users"]
farms_collection = db["farms"]
sensor_data_collection = db["sensor_data"]
history_collection = db["history"]
diseases_collection = db["diseases"]
topics_collection = db["topics"]
replies_collection = db["replies"]
notifications_collection = db["notifications"]