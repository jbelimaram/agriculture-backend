# routes/alerts.py
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime
from database import sensor_data_collection, notifications_collection
from auth_utils import verify_token_dependency

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])

@router.get("/{user_email}")
async def get_alerts(
    user_email: str,
    parcelle_id: Optional[str] = None,
    current_user=Depends(verify_token_dependency)
):
    """
    Génère des alertes actives pour un utilisateur à partir :
    - des dernières données capteurs (seuils)
    - des notifications récentes non lues de type alerte
    """
    # Vérification d'authentification : on peut seulement voir ses propres alertes
    if current_user["email"] != user_email and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    alerts = []

    # 1. Récupérer la dernière donnée capteur pour l'utilisateur (et optionnellement parcelle)
    query = {"user_email": user_email}
    if parcelle_id:
        query["parcelle_id"] = parcelle_id

    latest_sensor = await sensor_data_collection.find_one(query, sort=[("timestamp", -1)])

    if latest_sensor:
        timestamp = latest_sensor.get("timestamp", datetime.utcnow())

        # Humidité du sol
        soil = latest_sensor.get("soil_moisture")
        if soil is not None:
            if soil < 25:
                alerts.append({
                    "priority": "danger",
                    "title": "🌱 Sécheresse critique",
                    "message": f"Humidité du sol à {soil}%. Arrosage urgent recommandé.",
                    "timestamp": timestamp
                })
            elif soil < 35:
                alerts.append({
                    "priority": "warning",
                    "title": "💧 Sol sec",
                    "message": f"Humidité du sol à {soil}%. Envisagez l'arrosage.",
                    "timestamp": timestamp
                })
            elif soil > 80:
                alerts.append({
                    "priority": "warning",
                    "title": "💦 Excès d'eau",
                    "message": f"Humidité du sol à {soil}%. Risque de pourriture des racines.",
                    "timestamp": timestamp
                })

        # Température
        temp = latest_sensor.get("temperature")
        if temp is not None:
            if temp > 38:
                alerts.append({
                    "priority": "danger",
                    "title": "🔥 Canicule extrême",
                    "message": f"Température de {temp}°C. Protégez vos cultures (ombrage, arrosage).",
                    "timestamp": timestamp
                })
            elif temp > 35:
                alerts.append({
                    "priority": "warning",
                    "title": "🌞 Température élevée",
                    "message": f"Température de {temp}°C. Augmentez l'irrigation si nécessaire.",
                    "timestamp": timestamp
                })
            elif temp < 5:
                alerts.append({
                    "priority": "warning",
                    "title": "❄️ Risque de gel",
                    "message": f"Température à {temp}°C. Protégez vos cultures (voile d'hivernage).",
                    "timestamp": timestamp
                })

        # Humidité de l'air
        humidity = latest_sensor.get("air_humidity")
        if humidity is not None and humidity < 30:
            alerts.append({
                "priority": "info",
                "title": "💨 Air très sec",
                "message": f"Humidité de l'air à {humidity}%. Évaporation élevée, stress hydrique possible.",
                "timestamp": timestamp
            })

        # Luminosité (si disponible)
        light = latest_sensor.get("light_intensity")
        if light is not None and light > 80000:
            alerts.append({
                "priority": "info",
                "title": "☀️ Luminosité extrême",
                "message": f"Luminosité de {light} lx. Ombrez si les cultures sont sensibles.",
                "timestamp": timestamp
            })

    # 2. Ajouter les notifications récentes non lues de type alerte (optionnel)
    alert_types = ["alert_temp_high", "alert_temp_low", "alert_soil_dry", "alert_humidity_low",
                   "irrigation_cancelled", "irrigation_reduced"]
    cursor = notifications_collection.find({
        "user_email": user_email,
        "read": False,
        "type": {"$in": alert_types}
    }).sort("created_at", -1).limit(5)

    async for notif in cursor:
        alerts.append({
            "priority": "info",
            "title": notif.get("title", "Alerte"),
            "message": notif.get("message", ""),
            "timestamp": notif.get("created_at", datetime.utcnow())
        })

    # Trier par timestamp décroissant et limiter à 10 alertes
    alerts.sort(key=lambda x: x["timestamp"], reverse=True)
    # Convertir les datetime en chaînes ISO pour la sérialisation JSON
    for alert in alerts:
        if isinstance(alert["timestamp"], datetime):
            alert["timestamp"] = alert["timestamp"].isoformat()

    return alerts[:10]