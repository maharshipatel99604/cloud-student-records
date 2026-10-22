#!/bin/bash
# ============================================================================
# Amazon Linux 2023 EC2 Launch Template User Data Script
# Project: Student Record Management System (Flask + Gunicorn + Nginx + DynamoDB)
# Log file: /var/log/user-data.log
# ============================================================================

set -euxo pipefail

# 1. Redirect all stdout and stderr to /var/log/user-data.log and system logger
exec > >(tee /var/log/user-data.log | logger -t user-data -s 2>/dev/console) 2>&1

echo "=== [1/8] Starting Student Record App Bootstrap at $(date -u) ==="

# ============================================================================
# REQUIRED PLACEHOLDERS — UPDATE BEFORE PASTING INTO EC2 LAUNCH TEMPLATE
# ============================================================================
REPO_URL="https://github.com/maharshipatel99604/cloud-student-records.git"
AWS_REGION="ap-south-1"
DYNAMODB_TABLE_NAME="StudentRecords"
APP_DIR="/opt/student-record-app"
APP_USER="ec2-user"

echo "=== [2/8] Installing system packages via dnf (non-interactive) ==="
dnf update -y
dnf install -y python3 python3-pip git nginx

echo "=== [3/8] Cloning repository from ${REPO_URL} into ${APP_DIR} ==="
rm -rf "${APP_DIR}"
git clone "${REPO_URL}" "${APP_DIR}"

# Handle case where repository was pushed from a parent folder containing cloud-student-records/
if [ ! -f "${APP_DIR}/app.py" ] && [ -f "${APP_DIR}/cloud-student-records/app.py" ]; then
    echo "Detected nested cloud-student-records directory; moving files to ${APP_DIR}..."
    cp -a "${APP_DIR}/cloud-student-records/." "${APP_DIR}/"
fi

echo "=== [4/8] Creating Python virtual environment and installing dependencies ==="
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install --no-cache-dir -r "${APP_DIR}/requirements.txt"

# Generate a random Flask secret key for this instance
FLASK_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

# Set ownership so ec2-user can run the service cleanly
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "=== [5/8] Creating systemd service: /etc/systemd/system/student-app.service ==="
cat <<EOF > /etc/systemd/system/student-app.service
[Unit]
Description=Gunicorn WSGI Server for Student Record Management System
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="STORAGE_BACKEND=dynamodb"
Environment="DYNAMODB_TABLE_NAME=${DYNAMODB_TABLE_NAME}"
Environment="AWS_DEFAULT_REGION=${AWS_REGION}"
Environment="AWS_REGION=${AWS_REGION}"
Environment="FLASK_SECRET_KEY=${FLASK_SECRET_KEY}"
ExecStart=${APP_DIR}/.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 --access-logfile - --error-logfile - app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "=== [6/8] Configuring Nginx reverse proxy on port 80 -> 127.0.0.1:8000 ==="
cat <<'EOF' > /etc/nginx/conf.d/student-app.conf
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 4M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
    }
}
EOF

# Remove default server_name block inside /etc/nginx/nginx.conf if it conflicts with default_server
if grep -q "default_server" /etc/nginx/nginx.conf; then
    sed -i 's/default_server//g' /etc/nginx/nginx.conf
fi

nginx -t

echo "=== [7/8] Enabling and starting student-app and nginx services ==="
systemctl daemon-reload
systemctl enable student-app
systemctl restart student-app
systemctl enable nginx
systemctl restart nginx

echo "=== [8/8] Verifying local health endpoint ==="
sleep 3
curl -fsS http://127.0.0.1:8000/health || echo "Warning: Gunicorn health check not ready yet"
curl -fsS http://127.0.0.1/health || echo "Warning: Nginx health check not ready yet"

echo "=== Bootstrap completed successfully at $(date -u) ==="
