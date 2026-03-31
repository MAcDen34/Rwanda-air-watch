import asyncio
import sys
import os

# make sure shared/ is importable regardless of where we launch from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from shared.db import get_pool, init_db, close_pool
from ingestion.poller import poll_once, polling_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await init_db()
    # kick off background polling loop
    task = asyncio.create_task(polling_loop())
    yield
    # shutdown
    task.cancel()
    await close_pool()


app = FastAPI(title="Rwanda Air — Ingestion Worker", lifespan=lifespan)


@app.get("/health")
async def health():
    # nginx will hit this to check if we're alive
    return {"status": "ok", "worker": "ingestion"}


@app.post("/poll/now")
async def force_poll():
    """manually trigger a poll — handy for testing without waiting 5 mins"""
    await poll_once()
    return {"status": "polled"}


@app.get("/readings/latest")
async def latest_readings():
    """last reading per city — useful for the status dashboard"""
    pool = await get_pool()
    sql = """
        SELECT DISTINCT ON (city)
            city, pm25, pm10, no2, o3, aqi, recorded_at
        FROM readings
        ORDER BY city, recorded_at DESC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)

    return [dict(r) for r in rows]
