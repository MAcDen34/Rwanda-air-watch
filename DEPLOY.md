# Deployment Guide

## Order matters — do this sequence

### 1. Push your code to GitHub first
```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/rwanda-air.git
git push -u origin main
```

### 2. Set up web-01 (ingestion + postgres + redis)
```bash
ssh root@web-01-IP
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/rwanda-air/main/scripts/setup_web01.sh
chmod +x setup_web01.sh
./setup_web01.sh
```

Then edit the .env:
```bash
nano /opt/rwanda-air/.env
# fill in your real API keys
```

Allow web-02 to connect to postgres (run on web-01):
```bash
sudo -u postgres psql -c "ALTER SYSTEM SET listen_addresses = '*';"
echo "host airquality airuser WEB_02_IP/32 md5" >> /etc/postgresql/14/main/pg_hba.conf
systemctl restart postgresql
```

### 3. Set up web-02 (analysis worker)
```bash
ssh root@web-02-IP
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/rwanda-air/main/scripts/setup_web02.sh
chmod +x setup_web02.sh
./setup_web02.sh
```

Edit .env on web-02 — make sure DB_URL points to web-01:
```bash
nano /opt/rwanda-air/.env
# DB_URL=postgresql://airuser:airpass@WEB_01_IP:5432/airquality
# fill in API keys
```

Restart the service:
```bash
systemctl restart rwanda-air-analysis
```

### 4. Set up lb-01 (nginx)
```bash
ssh root@lb-01-IP
# edit the IPs in the script first
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/rwanda-air/main/scripts/setup_lb01.sh
nano setup_lb01.sh  # replace REPLACE_WITH_WEB01_IP and REPLACE_WITH_WEB02_IP
chmod +x setup_lb01.sh
./setup_lb01.sh
```

---

## Verify everything is working

```bash
# from your laptop

# both workers are alive
curl http://LB_IP/health

# latest readings (ingestion side)
curl http://LB_IP/readings/latest

# full status (analysis side)
curl http://LB_IP/status

# manually trigger a poll + analysis cycle
curl -X POST http://LB_IP/poll/now
curl -X POST http://LB_IP/analyze/now

# check recent alerts
curl http://LB_IP/alerts/recent
```

---

## Useful commands once running

```bash
# watch logs live
journalctl -u rwanda-air-ingestion -f   # on web-01
journalctl -u rwanda-air-analysis -f    # on web-02

# restart a worker after code changes
cd /opt/rwanda-air && git pull
systemctl restart rwanda-air-ingestion  # or rwanda-air-analysis

# nginx logs on lb-01
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

---

## Firewall rules to set (ufw)

On web-01:
```bash
ufw allow from LB_IP to any port 8001
ufw allow from WEB_02_IP to any port 5432  # postgres
```

On web-02:
```bash
ufw allow from LB_IP to any port 8002
```

On lb-01:
```bash
ufw allow 80
ufw allow 22
```
