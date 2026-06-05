import jwt
import secrets
from datetime import datetime, timedelta
from passlib.context import CryptContext
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from fastapi import HTTPException, Request
from config import SECRET_KEY, ALGORITHM, RESET_TOKEN_EXPIRE_MINUTES, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from database import users_collection

# Password hashing
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# OAuth client
oauth = OAuth(Config(environ={
    "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
    "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET
}))

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_jwt_token(data: dict, expires_delta: timedelta = timedelta(days=7)) -> str:
    expiration = datetime.utcnow() + expires_delta
    to_encode = data.copy()
    to_encode.update({"exp": expiration})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_reset_token(email: str) -> str:
    return create_jwt_token(
        {"email": email, "type": "reset"},
        expires_delta=timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    )

def decode_jwt_token(token: str):
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

def generate_oauth_state() -> str:
    return secrets.token_urlsafe(16)

# Dependency to verify token and return user info
async def verify_token_dependency(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = auth_header.split(" ")[1]
    try:
        payload = decode_jwt_token(token)
        email = payload.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await users_collection.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")