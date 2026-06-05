from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import httpx
import os

router = APIRouter(prefix="/api/weather", tags=["weather"])

# Clé API OpenWeatherMap
WEATHER_API_KEY = "d1a7be5bf70dc46506622a85d589d2f6"

@router.get("/current")
async def get_current_weather(lat: float, lon: float):
    """Récupère la météo actuelle (proxy pour éviter CORS)"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": WEATHER_API_KEY,
                    "units": "metric",
                    "lang": "fr"
                },
                timeout=10.0
            )
            return JSONResponse(content=response.json(), status_code=response.status_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/forecast")
async def get_weather_forecast(lat: float, lon: float):
    """Récupère les prévisions météo (proxy pour éviter CORS)"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": WEATHER_API_KEY,
                    "units": "metric",
                    "lang": "fr"
                },
                timeout=10.0
            )
            return JSONResponse(content=response.json(), status_code=response.status_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/by-city")
async def get_weather_by_city(city: str = "Tunis"):
    """Récupère la météo par nom de ville (proxy pour éviter CORS)"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q": city,
                    "appid": WEATHER_API_KEY,
                    "units": "metric",
                    "lang": "fr"
                },
                timeout=10.0
            )
            return JSONResponse(content=response.json(), status_code=response.status_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))