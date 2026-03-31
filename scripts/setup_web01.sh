#!/bin/bash
# run this on web-01 as root (or with sudo)
# sets up postgres, redis, python env, and the ingestion service

set -e

echo "=== web-01 setup: ingestion worker ==="

# 1. system deps
apt update && apt install -y python3.11 python3.11-venv python3-pip postgresql redis-server nginx git

# 2. postgres setup
# timescaledb needs its own repo
echo "--- setting up TimescaleDB ---"
apt install -y gnupg
curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /usr/share/keyrings/timescaledb.gpg
echo "deb [signed-by=/usr/share/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/timescaledb.list
apt update && apt install -y timescaledb-2-postgresql-14
timescaledb-tune --quiet --yes
systemctl restart postgresql

# create DB and user
sudo -u postgres psql <<EOF
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'airuser') THEN
      CREATE ROLE airuser LOGIN PASSWORD 'airpass';
   END IF;
END
\$\$;
CREATE DATABASE airquality OWNER airuser;
EOF

# 3. clone your repo (update this URL)
cd /opt
if [ ! -d "rwanda-air" ]; then
    git clone https://github.com/MAcDen34/Rwanda-air-watch.git
fi
cd rwanda-air

# 4. python virtual env
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. copy env file (you'll fill this in)
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ">>> EDIT /opt/rwanda-air/.env before starting the service <<<"
fi

# 6. systemd service for the ingestion worker
cat > /etc/systemd/system/rwanda-air-ingestion.service <<EOF
[Unit]
Description=Rwanda Air Ingestion Worker
After=network.target postgresql.service redis.service

[Service]
User=www-data
WorkingDirectory=/opt/rwanda-air
EnvironmentFile=/opt/rwanda-air/.env
ExecStart=/opt/rwanda-air/venv/bin/uvicorn ingestion.main:app --host 0.0.0.0 --port 8001 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable rwanda-air-ingestion
systemctl start rwanda-air-ingestion

echo "=== web-01 done ==="
echo "Check: systemctl status rwanda-air-ingestion"
echo "Logs:  journalctl -u rwanda-air-ingestion -f"
