# Rwanda Air Watch

A backend monitoring system that pulls real-time air quality data for three Rwandan cities — Kigali, Musanze, and Rubavu — detects pollution anomalies using Z-score analysis, and routes alerts through SMS and push notifications. Deployed across two application servers with an nginx load balancer.

---

## What it does

- Polls the Open-Meteo Air Quality API every 5 minutes for PM2.5, PM10, NO2, O3, and CO readings
- Stores readings in PostgreSQL with time-series indexing
- Runs statistical anomaly detection (Z-score with rolling hourly baseline per city per pollutant)
- Fires alerts via Africa's Talking SMS and ntfy.sh push notifications when a Z-score exceeds 2.5
- Deduplicates alerts using Redis so duplicate events don't fire twice
- Serves a REST API with city filtering, sorting, and history endpoints
- Includes a web frontend dashboard accessible through the load balancer

---


## Demo-video link

# Demo_video:

## Architecture

```
Client (browser / curl)
        |
   [lb-01: nginx]          -- round-robin load balancer
   /        \
[web-01]  [web-02]
ingestion  analysis
worker     worker
   \        /
  PostgreSQL (web-01)
  Redis     (web-01 + web-02)
```

- **web-01** runs the ingestion worker (FastAPI on port 8001) — polls Open-Meteo, writes readings to PostgreSQL
- **web-02** runs the analysis worker (FastAPI on port 8002) — reads readings, runs anomaly detection, fires alerts
- **lb-01** runs nginx — routes `/poll/` and `/readings/` to web-01, `/analyze/` and `/alerts/` to web-02, `/health` to both

---

## APIs Used

### Open-Meteo Air Quality API
- **URL**: https://open-meteo.com/en/docs/air-quality-api
- **Purpose**: Real-time air quality data (PM2.5, PM10, NO2, O3, CO) for Rwandan coordinates
- **Authentication**: No API key required — free and open
- **Rate limits**: No hard rate limit; we poll every 5 minutes per city
- **Credit**: Open-Meteo — open-source weather API, CC BY 4.0

### Africa's Talking SMS API
- **URL**: https://developers.africastalking.com/docs/sms/sending
- **Purpose**: SMS alert delivery when anomalies are detected
- **Authentication**: Username + API key (stored in `.env`, never committed)
- **Sandbox**: Use `AT_USERNAME=sandbox` and `AT_API_KEY=` for testing without sending real SMS
- **Credit**: Africa's Talking — African telecoms API platform

### ntfy.sh Push Notifications
- **URL**: https://ntfy.sh/docs
- **Purpose**: Push notification delivery as a secondary alert channel
- **Authentication**: No key required for public topics
- **Credit**: ntfy — open-source push notification service

---

## Local Setup

### Requirements
- Python 3.8+
- PostgreSQL 12+
- Redis

### Steps

```bash
git clone https://github.com/MAcDen34/Rwanda-air-watch.git
cd Rwanda-air-watch

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env — set DB_URL to your local postgres connection
```

Create the database:

```bash
sudo -u postgres psql
CREATE ROLE airuser LOGIN PASSWORD 'airpass';
CREATE DATABASE airquality OWNER airuser;
\q
```

Run the ingestion worker:

```bash
uvicorn ingestion.main:app --host 0.0.0.0 --port 8001 --reload
```

Run the analysis worker (separate terminal):

```bash
uvicorn analysis.main:app --host 0.0.0.0 --port 8002 --reload
```

Test it:

```bash
# trigger a poll
curl -X POST http://localhost:8001/poll/now

# check readings (all cities)
curl http://localhost:8001/readings/latest

# filter by city
curl "http://localhost:8001/readings/latest?city=Kigali"

# sort ascending
curl "http://localhost:8001/readings/latest?sort=asc"

# reading history for a city
curl "http://localhost:8001/readings/history?city=Musanze&limit=20"

# trigger analysis
curl -X POST http://localhost:8002/analyze/now

# check alerts
curl http://localhost:8002/alerts/recent
```


Using the CLI (Command line Interface):

  python3 cli.py latest
  python3 cli.py latest --city Kigali
  python3 cli.py alerts
  python3 cli.py poll

---

## Deployment

Servers:
- **web-01**: `3.95.187.87` (ingestion worker)
- **web-02**: `44.211.134.110` (analysis worker)
- **lb-01**: `18.207.186.124` (nginx load balancer)

### web-01 setup

```bash
ssh ubuntu@3.95.187.87

sudo apt update
sudo apt install -y python3.8-venv python3-pip postgresql redis-server nginx git

sudo -u postgres psql -c "CREATE ROLE airuser LOGIN PASSWORD 'airpass';"
sudo -u postgres psql -c "CREATE DATABASE airquality OWNER airuser;"

cd /opt
sudo git clone https://github.com/MAcDen34/Rwanda-air-watch.git
cd Rwanda-air-watch
sudo python3.8 -m venv venv
sudo venv/bin/pip install -r requirements.txt

sudo tee /opt/Rwanda-air-watch/.env << 'EOF'
DB_URL=postgresql://airuser:airpass@localhost:5432/airquality
REDIS_URL=redis://localhost:6379
AT_USERNAME=sandbox
AT_API_KEY=
AT_ALERT_PHONE=+250788000000
NTFY_TOPIC=rwanda-air-alerts
Z_SCORE_THRESHOLD=2.5
POLL_INTERVAL=300
EOF

sudo tee /etc/systemd/system/rwanda-air-ingestion.service << 'EOF'
[Unit]
Description=Rwanda Air Ingestion Worker
After=network.target postgresql.service redis.service

[Service]
User=ubuntu
WorkingDirectory=/opt/Rwanda-air-watch
EnvironmentFile=/opt/Rwanda-air-watch/.env
ExecStart=/opt/Rwanda-air-watch/venv/bin/uvicorn ingestion.main:app --host 0.0.0.0 --port 8001 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable rwanda-air-ingestion
sudo systemctl start rwanda-air-ingestion
```

Open PostgreSQL to web-02:

```bash
sudo -u postgres psql -c "ALTER SYSTEM SET listen_addresses = '*';"
echo "host airquality airuser 44.211.134.110/32 md5" | sudo tee -a /etc/postgresql/12/main/pg_hba.conf
sudo systemctl restart postgresql
```

### web-02 setup

```bash
ssh ubuntu@44.211.134.110

sudo apt update
sudo apt install -y python3.8-venv python3-pip redis-server git

cd /opt
sudo git clone https://github.com/MAcDen34/Rwanda-air-watch.git
cd Rwanda-air-watch
sudo python3.8 -m venv venv
sudo venv/bin/pip install -r requirements.txt

sudo tee /opt/Rwanda-air-watch/.env << 'EOF'
DB_URL=postgresql://airuser:airpass@3.95.187.87:5432/airquality
REDIS_URL=redis://localhost:6379
AT_USERNAME=sandbox
AT_API_KEY=
AT_ALERT_PHONE=+250788000000
NTFY_TOPIC=rwanda-air-alerts
Z_SCORE_THRESHOLD=2.5
POLL_INTERVAL=300
EOF

sudo tee /etc/systemd/system/rwanda-air-analysis.service << 'EOF'
[Unit]
Description=Rwanda Air Analysis Worker
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/Rwanda-air-watch
EnvironmentFile=/opt/Rwanda-air-watch/.env
ExecStart=/opt/Rwanda-air-watch/venv/bin/uvicorn analysis.main:app --host 0.0.0.0 --port 8002 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable rwanda-air-analysis
sudo systemctl start rwanda-air-analysis
```

### lb-01 setup

```bash
ssh ubuntu@18.207.186.124

sudo apt update
sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/rwanda-air << 'EOF'
upstream ingestion_workers {
    server 10.227.63.11:8001 max_fails=3 fail_timeout=30s;
}

upstream analysis_workers {
    server 10.227.107.141:8002 max_fails=3 fail_timeout=30s;
}

upstream all_workers {
    server 10.227.63.11:8001 max_fails=3 fail_timeout=30s;
    server 10.227.107.141:8002 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name _;

    location /health {
        proxy_pass http://all_workers;
        proxy_set_header Host $host;
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
    }

    location /poll/ {
        proxy_pass http://ingestion_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /readings/ {
        proxy_pass http://ingestion_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /analyze/ {
        proxy_pass http://analysis_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /alerts/ {
        proxy_pass http://analysis_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://all_workers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/rwanda-air /etc/nginx/sites-enabled/rwanda-air
sudo nginx -t
sudo systemctl start nginx
sudo systemctl enable nginx
```

---

## Deployment Notes and Challenges

**ARM architecture on AWS**: All three servers are aarch64 (ARM64). The deadsnakes PPA doesn't provide ARM builds for Ubuntu 20.04, so Python 3.11 was unavailable. Python 3.8 (bundled with the OS) was used instead. This required removing Python 3.10+ union type hints (`dict | None` → no annotation, `tuple[float, float] | None` → no annotation).

**TimescaleDB on ARM**: TimescaleDB doesn't publish ARM packages for Ubuntu 20.04. The hypertable calls were removed from `db.py` and standard PostgreSQL with a composite index on `(city, recorded_at)` was used instead. Performance is adequate for this scale.

**HAProxy conflict on lb-01**: The lb-01 server had an existing HAProxy process occupying port 80 from a previous project. It was stopped and disabled before nginx could start.

**Conflicting nginx config**: A leftover `nutritrack-lb` nginx site config was enabled on lb-01, causing all traffic to route to a different application. It was removed from `sites-enabled`.

**Private IP routing**: Using public IPs in the nginx upstream config caused 504 timeouts because AWS security groups were blocking inter-server traffic on ports 8001/8002. Switching to private subnet IPs (10.x.x.x) resolved this — traffic within the same VPC doesn't go through the security group in the same way.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Worker health check |
| POST | `/poll/now` | Trigger immediate data poll |
| GET | `/readings/latest` | Latest readings (all cities or filtered) |
| GET | `/readings/latest?city=Kigali` | Filter by city |
| GET | `/readings/latest?sort=asc` | Sort by AQI ascending |
| GET | `/readings/history?city=Musanze` | Historical readings for a city |
| POST | `/analyze/now` | Trigger anomaly detection |
| GET | `/alerts/recent` | Recent anomaly alerts |
| GET | `/status` | System status and stats |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DB_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `AT_USERNAME` | Africa's Talking username (use `sandbox` for testing) |
| `AT_API_KEY` | Africa's Talking API key |
| `AT_ALERT_PHONE` | Phone number to receive SMS alerts |
| `NTFY_TOPIC` | ntfy.sh topic name for push notifications |
| `Z_SCORE_THRESHOLD` | Anomaly detection sensitivity (default 2.5) |
| `POLL_INTERVAL` | Seconds between polls (default 300) |

Never commit `.env`. Use `.env.example` as the template.

---

## Credits

- [Open-Meteo](https://open-meteo.com) — free open-source weather and air quality API
- [Africa's Talking](https://africastalking.com) — SMS and telecoms API for Africa
- [ntfy.sh](https://ntfy.sh) — open-source push notification service
- [FastAPI](https://fastapi.tiangolo.com) — Python web framework
- [asyncpg](https://github.com/MagicStack/asyncpg) — async PostgreSQL driver
