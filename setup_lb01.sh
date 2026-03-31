#!/bin/bash
# run this on lb-01 as root
# pure nginx — no python, no app code

set -e

echo "=== lb-01 setup: nginx load balancer ==="

apt update && apt install -y nginx

# grab the nginx config from the repo
# (or just paste it manually if you prefer)
WEB01_IP="REPLACE_WITH_WEB01_IP"
WEB02_IP="REPLACE_WITH_WEB02_IP"

# copy config and substitute real IPs
cat /dev/stdin > /etc/nginx/sites-available/rwanda-air <<NGINX
upstream ingestion_workers {
    server ${WEB01_IP}:8001 max_fails=3 fail_timeout=30s;
}

upstream analysis_workers {
    server ${WEB02_IP}:8002 max_fails=3 fail_timeout=30s;
}

upstream all_workers {
    server ${WEB01_IP}:8001 max_fails=3 fail_timeout=30s;
    server ${WEB02_IP}:8002 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name _;

    location /health {
        proxy_pass http://all_workers;
        proxy_set_header Host \$host;
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
    }

    location /poll/ {
        proxy_pass http://ingestion_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /readings/ {
        proxy_pass http://ingestion_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /analyze/ {
        proxy_pass http://analysis_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /alerts/ {
        proxy_pass http://analysis_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /status {
        proxy_pass http://all_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location / {
        proxy_pass http://all_workers;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
NGINX

# disable default site, enable ours
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/rwanda-air /etc/nginx/sites-enabled/rwanda-air

nginx -t  # test config before reloading
systemctl reload nginx
systemctl enable nginx

echo "=== lb-01 done ==="
echo ""
echo "Test it:"
echo "  curl http://lb-01-IP/health"
echo "  curl http://lb-01-IP/status"
echo "  curl -X POST http://lb-01-IP/poll/now"
echo "  curl -X POST http://lb-01-IP/analyze/now"
