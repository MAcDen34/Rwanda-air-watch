import asyncio
import httpx
from datetime import datetime

from shared.config import CITIES, OWM_API_KEY, POLL_INTERVAL
from shared.db import get_pool


# open-meteo is free and doesn't need an API key — nice
# returns air quality index values for a lat/lon
async def fetch_open_meteo(city: str, lat: float, lon: float):
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=pm10,pm2_5,nitrogen_dioxide,ozone,carbon_monoxide,european_aqi"
        "&forecast_days=1"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        hourly = data.get("hourly", {})
        # just grab the most recent hour's values
        idx = -1  # last entry in the hourly array

        return {
            "city": city,
            "pm25": _safe(hourly.get("pm2_5"), idx),
            "pm10": _safe(hourly.get("pm10"), idx),
            "no2":  _safe(hourly.get("nitrogen_dioxide"), idx),
            "o3":   _safe(hourly.get("ozone"), idx),
            "co":   _safe(hourly.get("carbon_monoxide"), idx),
            "aqi":  _safe(hourly.get("european_aqi"), idx),
        }
    except Exception as e:
        print(f"[poller] failed to fetch {city}: {e}")
        return None


def _safe(arr, idx):
    """pull a value out of a list without blowing up if it's None or empty"""
    if not arr:
        return None
    try:
        val = arr[idx]
        return float(val) if val is not None else None
    except (IndexError, TypeError, ValueError):
        return None


async def store_reading(pool, reading: dict):
    sql = """
        INSERT INTO readings (city, pm25, pm10, no2, o3, co, aqi)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """
    async with pool.acquire() as conn:
        await conn.execute(
            sql,
            reading["city"],
            reading["pm25"],
            reading["pm10"],
            reading["no2"],
            reading["o3"],
            reading["co"],
            reading["aqi"],
        )


async def poll_once():
    pool = await get_pool()
    tasks = [
        fetch_open_meteo(city, info["lat"], info["lon"])
        for city, info in CITIES.items()
    ]
    results = await asyncio.gather(*tasks)

    saved = 0
    for r in results:
        if r:
            await store_reading(pool, r)
            saved += 1

    print(f"[{datetime.utcnow().isoformat()}] polled — saved {saved}/{len(CITIES)} cities")


async def polling_loop():
    while True:
        try:
            await poll_once()
        except Exception as e:
            # don't let one bad poll kill the whole loop
            print(f"[poller] unexpected error: {e}")
        await asyncio.sleep(POLL_INTERVAL)
