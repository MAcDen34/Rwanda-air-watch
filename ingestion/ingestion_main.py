import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from shared.db import get_pool, init_db, close_pool
from ingestion.poller import poll_once, polling_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # start background polling loop - sleeps 60s first so DB is settled
    asyncio.create_task(polling_loop())
    yield
    await close_pool()


app = FastAPI(title="Rwanda Air - Ingestion Worker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "worker": "ingestion"}


@app.post("/poll/now")
async def poll_now():
    # manually trigger a poll instead of waiting for the scheduler
    results = await poll_once()
    return {"polled": len(results), "cities": [r["city"] for r in results]}


@app.get("/readings/latest")
async def latest_readings(
    city: Optional[str] = Query(None, description="Filter by city name e.g. Kigali"),
    limit: int = Query(10, ge=1, le=100, description="Number of readings to return"),
    sort: str = Query("desc", description="Sort by time: asc or desc"),
):
    pool = await get_pool()

    order = "DESC" if sort.lower() != "asc" else "ASC"

    if city:
        # filter to a specific city - case-insensitive match
        sql = f"""
            SELECT city, pm25, pm10, no2, o3, co, aqi, recorded_at
            FROM readings
            WHERE LOWER(city) = LOWER($1)
            ORDER BY recorded_at {order}
            LIMIT $2
        """
        rows = await pool.fetch(sql, city, limit)
    else:
        # return latest reading per city by default
        sql = f"""
            SELECT DISTINCT ON (city) city, pm25, pm10, no2, o3, co, aqi, recorded_at
            FROM readings
            ORDER BY city, recorded_at {order}
            LIMIT $1
        """
        rows = await pool.fetch(sql, limit)

    return [
        {
            "city": r["city"],
            "pm25": r["pm25"],
            "pm10": r["pm10"],
            "no2": r["no2"],
            "o3": r["o3"],
            "co": r["co"],
            "aqi": r["aqi"],
            "recorded_at": r["recorded_at"].isoformat() if r["recorded_at"] else None,
        }
        for r in rows
    ]


@app.get("/readings/history")
async def reading_history(
    city: str = Query(..., description="City name e.g. Kigali"),
    limit: int = Query(50, ge=1, le=500),
):
    # last N readings for a city - useful for charting trends
    pool = await get_pool()
    sql = """
        SELECT city, pm25, pm10, no2, o3, aqi, recorded_at
        FROM readings
        WHERE LOWER(city) = LOWER($1)
        ORDER BY recorded_at DESC
        LIMIT $2
    """
    rows = await pool.fetch(sql, city, limit)
    return [
        {
            "city": r["city"],
            "pm25": r["pm25"],
            "pm10": r["pm10"],
            "no2": r["no2"],
            "o3": r["o3"],
            "aqi": r["aqi"],
            "recorded_at": r["recorded_at"].isoformat() if r["recorded_at"] else None,
        }
        for r in rows
    ]


@app.get("/status")
async def status():
    pool = await get_pool()
    count = await pool.fetchval("SELECT COUNT(*) FROM readings")
    latest = await pool.fetchrow(
        "SELECT recorded_at FROM readings ORDER BY recorded_at DESC LIMIT 1"
    )
    return {
        "worker": "ingestion",
        "total_readings": count,
        "last_poll": latest["recorded_at"].isoformat() if latest else None,
        "cities": ["Kigali", "Musanze", "Rubavu"],
    }
