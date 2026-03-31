import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from shared.db import get_pool, init_db, close_pool
from shared.config import POLL_INTERVAL
from analysis.detector import check_latest_readings
from analysis.alerter import route_alerts


async def analysis_loop():
    # runs slightly offset from the ingestion loop so fresh data is usually ready
    await asyncio.sleep(60)
    while True:
        try:
            anomalies = await check_latest_readings()
            if anomalies:
                print(f"[analysis] found {len(anomalies)} anomalies, routing alerts...")
                await route_alerts(anomalies)
            else:
                print("[analysis] no anomalies this cycle")
        except Exception as e:
            print(f"[analysis] error in loop: {e}")
        await asyncio.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(analysis_loop())
    yield
    task.cancel()
    await close_pool()


app = FastAPI(title="Rwanda Air — Analysis Worker", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "worker": "analysis"}


@app.post("/analyze/now")
async def force_analysis():
    """trigger analysis manually — good for demoing"""
    anomalies = await check_latest_readings()
    fired = await route_alerts(anomalies)
    return {
        "anomalies_found": len(anomalies),
        "alerts_fired": len(fired),
        "detail": fired,
    }


@app.get("/alerts/recent")
async def recent_alerts(limit: int = 20):
    pool = await get_pool()
    sql = """
        SELECT city, pollutant, z_score, value, fired_at, channel, delivered
        FROM alerts
        ORDER BY fired_at DESC
        LIMIT $1
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, limit)
    return [dict(r) for r in rows]


@app.get("/status")
async def full_status():
    """combined status endpoint — this is what you'd show on a dashboard"""
    pool = await get_pool()

    # latest reading per city
    readings_sql = """
        SELECT DISTINCT ON (city)
            city, pm25, pm10, no2, o3, aqi, recorded_at
        FROM readings
        ORDER BY city, recorded_at DESC
    """
    # last 5 alerts
    alerts_sql = """
        SELECT city, pollutant, z_score, value, fired_at
        FROM alerts
        ORDER BY fired_at DESC
        LIMIT 5
    """

    async with pool.acquire() as conn:
        readings = await conn.fetch(readings_sql)
        alerts   = await conn.fetch(alerts_sql)

    return {
        "latest_readings": [dict(r) for r in readings],
        "recent_alerts": [dict(r) for r in alerts],
    }
