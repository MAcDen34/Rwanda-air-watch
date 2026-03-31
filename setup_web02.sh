#!/bin/bash
# run this on web-02 as root
# web-02 only needs python + access to the same postgres on web-01
# no local postgres needed here — it connects remotely

set -e

echo "=== web-02 setup: analysis worker ==="

# 1. deps — no postgres here, just the client lib
apt update && apt install -y python3.11 python3.11-venv python3-pip git

# 2. clone repo
cd /opt
if [ ! -d "rwanda-air" ]; then
    git clone https://github.com/YOUR_USERNAME/rwanda-air.git
fi
cd rwanda-air

# 3. venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. env file — DB_URL here points to web-01's postgres
if [ ! -f ".env" ]; then
    cp .env.example .env
    # update DB_URL to point at web-01
    sed -i 's|localhost:5432|WEB_01_IP:5432|g' .env
    echo ">>> EDIT /opt/rwanda-air/.env — set your real API keys and WEB_01_IP <<<"
fi

# 5. allow web-02 to connect to postgres on web-01
# on web-01 you'll need to run:
#   sudo -u postgres psql -c "ALTER SYSTEM SET listen_addresses = '*';"
#   echo "host airquality airuser WEB_02_IP/32 md5" >> /etc/postgresql/14/main/pg_hba.conf
#   systemctl restart postgresql
# (setup_web01.sh doesn't do this automatically — do it manually so you understand it)

# 6. systemd for analysis worker
cat > /etc/systemd/system/rwanda-air-analysis.service <<EOF
[Unit]
Description=Rwanda Air Analysis Worker
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/rwanda-air
EnvironmentFile=/opt/rwanda-air/.env
ExecStart=/opt/rwanda-air/venv/bin/uvicorn analysis.main:app --host 0.0.0.0 --port 8002 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable rwanda-air-analysis
systemctl start rwanda-air-analysis

echo "=== web-02 done ==="
echo "Check: systemctl status rwanda-air-analysis"
echo "Logs:  journalctl -u rwanda-air-analysis -f"
