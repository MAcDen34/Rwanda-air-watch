import asyncpg
from shared.config import DB_URL

# just a module-level pool we reuse everywhere
_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# run this once on first deploy to create tables
CREATE_TABLES_SQL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS readings (
    id          BIGSERIAL,
    city        TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pm25        FLOAT,
    pm10        FLOAT,
    no2         FLOAT,
    o3          FLOAT,
    co          FLOAT,
    aqi         INT
);

-- turn it into a hypertable partitioned by time
SELECT create_hypertable('readings', 'recorded_at', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_readings_city_time ON readings (city, recorded_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id          BIGSERIAL PRIMARY KEY,
    city        TEXT NOT NULL,
    pollutant   TEXT NOT NULL,
    z_score     FLOAT NOT NULL,
    value       FLOAT NOT NULL,
    fired_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    channel     TEXT,          -- 'sms' or 'push'
    delivered   BOOLEAN DEFAULT FALSE
);
"""


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
    print("DB tables ready")
