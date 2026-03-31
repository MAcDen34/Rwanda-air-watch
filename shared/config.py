import os
from dotenv import load_dotenv

load_dotenv()

# postgres
DB_URL = os.getenv("DB_URL", "postgresql://airuser:airpass@localhost:5432/airquality")

# redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# open-meteo doesn't need a key, but openweathermap does
OWM_API_KEY = os.getenv("OWM_API_KEY", "")

# africa's talking
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
AT_API_KEY  = os.getenv("AT_API_KEY", "")
AT_PHONE    = os.getenv("AT_ALERT_PHONE", "+250788000000")  # who gets the SMS

# ntfy topic for push alerts
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "rwanda-air-alerts")

# cities we care about with their coordinates
CITIES = {
    "Kigali":  {"lat": -1.9441, "lon": 30.0619},
    "Musanze": {"lat": -1.4994, "lon": 29.6340},
    "Rubavu":  {"lat": -1.6839, "lon": 29.2583},  # close to Nyiragongo, matters a lot
}

# anomaly thresholds — how many std deviations before we care
Z_SCORE_THRESHOLD = float(os.getenv("Z_SCORE_THRESHOLD", "2.5"))

# how often the poller runs in seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))  # every 5 mins
