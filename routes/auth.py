import jwt
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Body
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime, timedelta
from models import (
    UserRegister, ResetPasswordRequest, SetPasswordRequest, ResetPasswordConfirm
)
from routes.notifications import create_notification
from database import users_collection, farms_collection
from auth_utils import (
    hash_password, verify_password, create_jwt_token, create_reset_token,
    decode_jwt_token, generate_oauth_state, oauth
)
from email_utils import send_reset_email
from config import FRONTEND_URL, SECRET_KEY, ALGORITHM

router = APIRouter(tags=["Authentication"])

# ---------- Email/Password Auth ----------
@router.post("/register")
async def register(user: UserRegister):
    existing = await users_collection.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    
    user_dict = user.dict()
    user_dict["password"] = hash_password(user.password)
    user_dict["username"] = f"{user.firstName} {user.lastName}"
    user_dict["provider"] = "email"
    user_dict["role"] = "agriculteur"
    user_dict["has_password"] = True
    user_dict["created_at"] = datetime.utcnow()
    
    await users_collection.insert_one(user_dict)
    
    # Notification de bienvenue
    await create_notification(
        user_email=user.email,
        type="welcome",
        title="Bienvenue sur AgriTunisie",
        message="Votre compte a été créé avec succès. Commencez à configurer votre ferme !",
        icon="fa-smile-wink"
    )
    
    return {"status": "success", "email": user.email}

@router.post("/login")
async def login(credentials: dict = Body(...)):
    email = credentials.get("email")
    password = credentials.get("password")
    
    user = await users_collection.find_one({"email": email})
    if not user or not verify_password(password, user["password"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    
    if "role" not in user:
        await users_collection.update_one({"email": email}, {"$set": {"role": "agriculteur"}})
        user["role"] = "agriculteur"
    
    farm = await farms_collection.find_one({"user_email": email})
    
    # Generate JWT token
    token = create_jwt_token({
        "email": user["email"],
        "role": user.get("role", "agriculteur")
    })
    
    return {
        "email": user["email"],
        "username": user.get("username", "Agriculteur"),
        "hasFarm": farm is not None,
        "role": user.get("role", "agriculteur"),
        "token": token
    }

@router.get("/check-email")
async def check_email(email: str):
    user = await users_collection.find_one({"email": email})
    return {"available": user is None}

# ---------- Password Reset ----------
@router.post("/forgot-password")
async def forgot_password(request: ResetPasswordRequest, background_tasks: BackgroundTasks):
    user = await users_collection.find_one({"email": request.email})
    if not user:
        return {"message": "Si cet email existe, un lien de réinitialisation a été envoyé."}
    
    token = create_reset_token(request.email)
    reset_link = f"{FRONTEND_URL}/reset-password?token={token}"
    background_tasks.add_task(send_reset_email, request.email, reset_link)
    return {"message": "Si cet email existe, un lien de réinitialisation a été envoyé."}

@router.get("/verify-reset-token")
async def verify_reset_token(token: str):
    try:
        payload = decode_jwt_token(token)
        if payload.get("type") != "reset":
            raise HTTPException(status_code=400, detail="Invalid token type")
        email = payload.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Invalid token")
        user = await users_collection.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"valid": True}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")

@router.post("/reset-password/confirm")
async def reset_password_confirm(data: ResetPasswordConfirm):
    """
    Confirme la réinitialisation du mot de passe avec le token reçu par email.
    """
    try:
        payload = decode_jwt_token(data.token)
        if payload.get("type") != "reset":
            raise HTTPException(status_code=400, detail="Type de token invalide")
        email = payload.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Token invalide")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Le lien a expiré. Veuillez refaire une demande.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Token invalide ou corrompu.")
    
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères.")
    
    hashed = hash_password(data.new_password)
    await users_collection.update_one(
        {"email": email},
        {"$set": {"password": hashed, "has_password": True}}
    )
    
    return {"message": "Mot de passe réinitialisé avec succès."}

@router.post("/set-password")
async def set_password(request: Request, data: SetPasswordRequest):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header.split(" ")[1]
    try:
        payload = decode_jwt_token(token)
        email = payload.get("email")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")
    
    hashed = hash_password(data.password)
    await users_collection.update_one(
        {"email": email},
        {"$set": {"password": hashed, "has_password": True}}
    )
    return {"message": "Password set successfully"}

# ---------- Google OAuth ----------
@router.get('/login/google')
async def google_login(request: Request):
    state = generate_oauth_state()
    request.session['oauth_state'] = state
    redirect_uri = request.url_for('google_auth')
    return await oauth.google.authorize_redirect(request, redirect_uri, state=state)

@router.get('/auth/google', name="google_auth")
async def google_auth(request: Request):
    expected_state = request.session.get('oauth_state')
    if not expected_state or request.query_params.get('state') != expected_state:
        return JSONResponse(status_code=400, content={"error": "Invalid state parameter"})

    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    if not user_info:
        return JSONResponse(status_code=400, content={"error": "Failed to get user info"})

    email = user_info['email']
    existing_user = await users_collection.find_one({"email": email})

    if not existing_user:
        name_parts = user_info.get('name', '').split(' ', 1)
        first_name = name_parts[0] if name_parts else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        user_data = {
            "email": email,
            "username": user_info.get('name', ''),
            "firstName": first_name,
            "lastName": last_name,
            "phone": "",
            "password": None,
            "has_password": False,
            "google_id": user_info['sub'],
            "picture": user_info.get('picture', ''),
            "provider": "google",
            "created_at": datetime.utcnow(),
            "role": "agriculteur"
        }
        await users_collection.insert_one(user_data)
        
        # Notification de bienvenue pour nouvel utilisateur Google
        await create_notification(
            user_email=email,
            type="welcome",
            title="Bienvenue sur AgriTunisie",
            message="Votre compte Google a été connecté. Complétez votre profil et votre ferme !",
            icon="fa-smile-wink"
        )
        
        existing_user = user_data
    else:
        updates = {}
        if "role" not in existing_user:
            updates["role"] = "agriculteur"
        if "has_password" not in existing_user:
            updates["has_password"] = existing_user.get("password") is not None
        if existing_user.get("password") is not None and not existing_user.get("has_password", False):
            updates["has_password"] = True
        if updates:
            await users_collection.update_one({"email": email}, {"$set": updates})
            existing_user.update(updates)

    farm = await farms_collection.find_one({"user_email": email})
    has_farm = farm is not None

    jwt_token = create_jwt_token({
        "email": email,
        "username": existing_user.get("username", ""),
        "hasFarm": has_farm,
        "role": existing_user.get("role", "agriculteur"),
        "has_password": existing_user.get("has_password", False)
    })

    redirect_url = f"{FRONTEND_URL}/auth-callback?token={jwt_token}"
    return RedirectResponse(url=redirect_url)