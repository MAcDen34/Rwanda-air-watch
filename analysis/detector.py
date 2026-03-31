import math
from shared.db import get_pool
from shared.config import Z_SCORE_THRESHOLD


# we compute a rolling baseline per city, per pollutant, per hour-of-day
# this avoids flagging normal morning peaks as anomalies
POLLUTANTS = ["pm25", "pm10", "no2", "o3", "co"]


async def get_baseline(pool, city: str, pollutant: str, hour: int) -> tuple[float, float] | None:
    """
    returns (mean, stddev) for a city+pollutant+hour combo
    looks at the last 7 days of data for that same hour window
    """
    sql = f"""
        SELECT AVG({pollutant}), STDDEV({pollutant})
        FROM readings
        WHERE city = $1
          AND EXTRACT(HOUR FROM recorded_at) = $2
          AND recorded_at > NOW() - INTERVAL '7 days'
          AND {pollutant} IS NOT NULL
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, city, hour)

    if not row or row[0] is None or row[1] is None:
        return None

    mean, std = float(row[0]), float(row[1])
    # if std is basically zero, skip — can't compute z-score
    if std < 0.0001:
        return None

    return mean, std


async def compute_z_score(value: float, mean: float, std: float) -> float:
    return (value - mean) / std


async def check_latest_readings() -> list[dict]:
    """
    grabs the most recent reading per city and checks each pollutant
    returns a list of anomaly dicts (empty list = nothing weird)
    """
    pool = await get_pool()
    anomalies = []

    sql = """
        SELECT DISTINCT ON (city)
            city, pm25, pm10, no2, o3, co, aqi, recorded_at
        FROM readings
        ORDER BY city, recorded_at DESC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)

    for row in rows:
        city = row["city"]
        hour = row["recorded_at"].hour

        for pollutant in POLLUTANTS:
            value = row[pollutant]
            if value is None:
                continue

            baseline = await get_baseline(pool, city, pollutant, hour)
            if baseline is None:
                # not enough history yet, skip
                continue

            mean, std = baseline
            z = await compute_z_score(value, mean, std)

            if abs(z) >= Z_SCORE_THRESHOLD:
                anomalies.append({
                    "city": city,
                    "pollutant": pollutant,
                    "value": value,
                    "mean": round(mean, 3),
                    "std": round(std, 3),
                    "z_score": round(z, 3),
                    "direction": "high" if z > 0 else "low",
                })

    return anomalies


async def save_alert(pool, anomaly: dict, channel: str, delivered: bool):
    sql = """
        INSERT INTO alerts (city, pollutant, z_score, value, channel, delivered)
        VALUES ($1, $2, $3, $4, $5, $6)
    """
    async with pool.acquire() as conn:
        await conn.execute(
            sql,
            anomaly["city"],
            anomaly["pollutant"],
            anomaly["z_score"],
            anomaly["value"],
            channel,
            delivered,
        )
