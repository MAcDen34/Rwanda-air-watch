import httpx
import redis.asyncio as aioredis
import hashlib
import json

from shared.config import AT_USERNAME, AT_API_KEY, AT_PHONE, NTFY_TOPIC, REDIS_URL


def _dedup_key(anomaly: dict) -> str:
    # key is city+pollutant+rounded z_score — same alert within 30 mins won't fire twice
    raw = f"{anomaly['city']}:{anomaly['pollutant']}:{int(anomaly['z_score'])}"
    return "alert:sent:" + hashlib.md5(raw.encode()).hexdigest()


async def already_sent(r, anomaly: dict) -> bool:
    key = _dedup_key(anomaly)
    return await r.exists(key)


async def mark_sent(r, anomaly: dict, ttl_seconds: int = 1800):
    key = _dedup_key(anomaly)
    await r.set(key, "1", ex=ttl_seconds)  # expires after 30 mins


def _build_message(anomaly: dict) -> str:
    direction = "spike" if anomaly["direction"] == "high" else "drop"
    return (
        f"[Rwanda Air Alert] {anomaly['city']} — "
        f"{anomaly['pollutant'].upper()} {direction} detected. "
        f"Value: {anomaly['value']:.1f}, Z-score: {anomaly['z_score']:.2f}. "
        f"Check dashboard for details."
    )


async def send_sms(message: str) -> bool:
    if not AT_API_KEY or AT_USERNAME == "sandbox":
        # sandbox mode — just print, don't actually send
        print(f"[SMS sandbox] {message}")
        return True

    url = "https://api.africastalking.com/version1/messaging"
    headers = {
        "apiKey": AT_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "username": AT_USERNAME,
        "to": AT_PHONE,
        "message": message,
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(url, data=payload, headers=headers)
            resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[alerter] SMS failed: {e}")
        return False


async def send_push(message: str) -> bool:
    # ntfy.sh is super simple — just POST to a topic URL
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            resp = await client.post(
                url,
                content=message.encode(),
                headers={
                    "Title": "Rwanda Air Quality Alert",
                    "Priority": "high",
                    "Tags": "warning,rwanda",
                },
            )
            resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[alerter] push notification failed: {e}")
        return False


async def route_alerts(anomalies: list[dict]) -> list[dict]:
    """
    takes a list of anomalies, deduplicates, fires SMS + push for each new one
    returns list of what was actually sent
    """
    if not anomalies:
        return []

    r = await aioredis.from_url(REDIS_URL)
    fired = []

    for anomaly in anomalies:
        if await already_sent(r, anomaly):
            print(f"[alerter] skipping duplicate: {anomaly['city']} {anomaly['pollutant']}")
            continue

        msg = _build_message(anomaly)

        sms_ok  = await send_sms(msg)
        push_ok = await send_push(msg)

        if sms_ok or push_ok:
            await mark_sent(r, anomaly)
            fired.append({**anomaly, "sms": sms_ok, "push": push_ok})
            print(f"[alerter] fired alert for {anomaly['city']} {anomaly['pollutant']}")

    await r.aclose()
    return fired
