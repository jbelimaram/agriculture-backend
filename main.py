from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from config import SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from auth_utils import oauth
from routes import auth, farm, sensors, history, admin, public_diseases, forum,weather,notifications,rendement,disease_prediction,alerts
from fastapi.staticfiles import StaticFiles
import os

# Créer le dossier uploads s'il n'existe pas
os.makedirs("uploads", exist_ok=True)
os.makedirs("uploads/forum", exist_ok=True)

app = FastAPI(title="AgriTunisie API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Accepte toutes les origines
    allow_credentials=False,      # Désactivé car incompatible avec "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'redirect_uri': 'http://127.0.0.1:8000/auth/google'
    }
)

app.include_router(auth.router)
app.include_router(farm.router)
app.include_router(sensors.router)
app.include_router(history.router)
app.include_router(admin.router)
app.include_router(public_diseases.router)
app.include_router(forum.router)
app.include_router(notifications.router)
app.include_router(weather.router)
app.include_router(rendement.router)
app.include_router(disease_prediction.router)
app.include_router(alerts.router) 

# Monter le dossier uploads pour le servir statiquement
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.on_event("startup")
async def startup_event():
    print("✅ AgriTunisie backend started successfully")
    print(f"📁 Uploads folder: {os.path.abspath('uploads')}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)