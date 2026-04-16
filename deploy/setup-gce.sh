#!/bin/bash
# GCE VM setup script for YTSage backend
# Run this on a fresh Ubuntu 22.04+ VM:
#   curl -sSL https://raw.githubusercontent.com/.../deploy/setup-gce.sh | bash
#
# Prerequisites: Create a GCE e2-small VM with Ubuntu 22.04, HTTP/HTTPS traffic allowed

set -e

echo "=== YTSage Backend Setup ==="

# System packages
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3-pip ffmpeg git nginx certbot python3-certbot-nginx

# Clone repo (or you can scp/rsync)
if [ ! -d "/opt/ytsage" ]; then
    echo "=== Cloning repository ==="
    sudo mkdir -p /opt/ytsage
    sudo chown $USER:$USER /opt/ytsage
    echo "Please clone or copy your repo to /opt/ytsage"
    echo "  e.g.: git clone <your-repo-url> /opt/ytsage"
    echo "Then re-run this script."
    exit 1
fi

cd /opt/ytsage/backend

# Python venv + deps
echo "=== Setting up Python environment ==="
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "=== IMPORTANT ==="
    echo "Edit /opt/ytsage/backend/.env and add your API keys:"
    echo "  OPENAI_API_KEY=sk-..."
    echo "  REPLICATE_API_TOKEN=r8_..."
    echo "  CORS_ORIGINS=https://your-frontend-domain.vercel.app"
    echo ""
fi

# Create data directories
mkdir -p cache/videos chroma_db

# Systemd service
echo "=== Creating systemd service ==="
sudo tee /etc/systemd/system/ytsage.service > /dev/null << 'EOF'
[Unit]
Description=YTSage Backend API
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/opt/ytsage/backend
ExecStart=/opt/ytsage/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5
Environment=PATH=/opt/ytsage/backend/venv/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ytsage
sudo systemctl start ytsage

# Nginx reverse proxy
echo "=== Configuring Nginx ==="
sudo tee /etc/nginx/sites-available/ytsage > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/ytsage /etc/nginx/sites-enabled/ytsage
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

echo ""
echo "=== Setup complete ==="
echo "Backend running at http://$(curl -s ifconfig.me):80"
echo ""
echo "Next steps:"
echo "  1. Edit /opt/ytsage/backend/.env with your API keys"
echo "  2. sudo systemctl restart ytsage"
echo "  3. Set CORS_ORIGINS in .env to your Vercel frontend URL"
echo "  4. For HTTPS: sudo certbot --nginx -d your-domain.com"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status ytsage    # check status"
echo "  sudo journalctl -u ytsage -f    # view logs"
echo "  sudo systemctl restart ytsage   # restart after .env changes"
