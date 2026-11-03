# Deploying AgroEcoAdvisor for the validation (single server, HTTPS)

**Target:** one Ubuntu 24.04 server running the backend (FastAPI + model + rasters + RAG + graph), the frontend (Next.js standalone) and Caddy (automatic HTTPS). Everything runs the way it runs on the development machine today: no Docker, no container rebuilds.

**Why this shape.** The app needs about 1.3 GB of data beside the code (724 MB raster stack, 501 MB Chroma index, 103 MB corpus) that is not on GitHub, plus an OpenAI key. A plain server takes those as files. The repo's `docker-compose.yml` predates the RAG layer and would need rework; not for tomorrow.

**What you need before starting**

- A DigitalOcean account (credit card), or any provider that gives an Ubuntu 24.04 VM with a public IP.
- The OpenAI API key from `app/backend/.env` on the dev machine.
- PowerShell on the dev machine (`ssh`, `scp` and `tar` are built in on Windows 10/11).
- About 1.5 GB of upload. At 10 Mbit/s that is 20 minutes.

Names used below: server IP `SERVER_IP`, hostname `agroecoadvisor.duckdns.org`. Replace both.

---

## 1. Server (DigitalOcean, 10 minutes)

1. Create → Droplets.
   - Region: Frankfurt or Amsterdam.
   - Image: Ubuntu 24.04 (LTS) x64.
   - Size: Basic → Regular → **8 GB RAM / 4 vCPU / 160 GB** (about $48/month, billed hourly; destroy it after the validation). 4 GB works but the Next.js build is slow on it.
   - Authentication: **SSH key** if you have one (`type $env:USERPROFILE\.ssh\id_ed25519.pub` in PowerShell; create one with `ssh-keygen -t ed25519` if not). Otherwise a root password.
   - Hostname: `agroecoadvisor`.
2. Note the public IPv4 address → `SERVER_IP`.
3. Networking → Firewalls (optional but good): inbound SSH 22, HTTP 80, HTTPS 443; outbound all.

## 2. Free hostname with HTTPS (5 minutes)

Voice input and "Use my location" only work on HTTPS, so the site needs a hostname.

1. Go to duckdns.org, sign in (Google or GitHub).
2. Add the subdomain `agroecoadvisor` (or any free name) and set its IP to `SERVER_IP`. Click update ip.
3. Check from PowerShell: `nslookup agroecoadvisor.duckdns.org` should return `SERVER_IP`.

## 3. Data archive (on the dev machine, PowerShell)

```powershell
cd C:\dev\agroadvisor-et
tar -czf C:\dev\agro-data.tgz geodata\layers rag\index\store rag\corpus\chunks.jsonl rag\corpus\manifest.jsonl rag\corpus\guidance rag\graph\store
dir C:\dev\agro-data.tgz
```

Expect roughly 1.0–1.3 GB.

## 4. Base install (on the server)

```powershell
ssh root@SERVER_IP
```

Then, on the server:

```bash
apt update && apt upgrade -y
apt install -y git python3.12-venv python3-pip build-essential ufw curl debian-keyring debian-archive-keyring apt-transport-https

# Node 22
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs

# Caddy (HTTPS reverse proxy)
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy

# Firewall
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable

# Code
git clone https://github.com/misge1233/agroecology-.git /srv/agroadvisor
```

## 5. Upload the data (dev machine, PowerShell; takes the longest)

```powershell
scp C:\dev\agro-data.tgz root@SERVER_IP:/srv/agroadvisor/
```

Then on the server:

```bash
cd /srv/agroadvisor && tar -xzf agro-data.tgz && rm agro-data.tgz
ls geodata/layers | wc -l        # expect 12 (11 tif + stack_all.vrt)
du -sh rag/index/store           # expect ~500M
ls rag/graph/store               # expect graph.json
```

## 6. Backend

```bash
cd /srv/agroadvisor
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r app/backend/requirements.txt -r rag/requirements.txt
```

Create `/srv/agroadvisor/app/backend/.env` (`nano app/backend/.env`), pasting the key by hand:

```
OPENAI_API_KEY=sk-...
ALLOWED_ORIGINS=https://agroecoadvisor.duckdns.org
LAYERS_DIR=/srv/agroadvisor/geodata/layers
SPEECH_LOCAL_ENABLED=false
CHAT_RATE_LIMIT_PER_MINUTE=30
```

`SPEECH_LOCAL_ENABLED=false` skips the 4 GB local Amharic/Oromo voice models; voice falls back to OpenAI audio and then to the browser's engines. The RAG index, corpus and graph paths default to the repo locations, so they need no setting.

Smoke test:

```bash
cd /srv/agroadvisor/app/backend
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second SSH window: `curl -s localhost:8000/health` → JSON with `"ok"`. Then `curl -s 'localhost:8000/metadata' | head -c 300`. Stop uvicorn with Ctrl-C.

Run it as a service, `nano /etc/systemd/system/agro-backend.service`:

```ini
[Unit]
Description=AgroEcoAdvisor backend
After=network.target

[Service]
WorkingDirectory=/srv/agroadvisor/app/backend
ExecStart=/srv/agroadvisor/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now agro-backend
systemctl status agro-backend --no-pager
journalctl -u agro-backend -n 30 --no-pager
```

## 7. Frontend

```bash
cd /srv/agroadvisor/app/frontend
cat > .env.production <<'EOF'
NEXT_PUBLIC_API_BASE_URL=https://agroecoadvisor.duckdns.org/api
NEXT_PUBLIC_APP_VERSION=validation-2026-11
EOF
npm ci
npm run build
```

The build takes 2–5 minutes. Service, `nano /etc/systemd/system/agro-frontend.service`:

```ini
[Unit]
Description=AgroEcoAdvisor frontend
After=network.target agro-backend.service

[Service]
WorkingDirectory=/srv/agroadvisor/app/frontend
ExecStart=/usr/bin/npm start
Environment=PORT=3000
Environment=HOSTNAME=127.0.0.1
Environment=NODE_ENV=production
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now agro-frontend
curl -s -o /dev/null -w "%{http_code}\n" localhost:3000/en     # expect 200
```

## 8. HTTPS with Caddy

`nano /etc/caddy/Caddyfile` — replace the whole file:

```
agroecoadvisor.duckdns.org {
    encode gzip

    handle_path /api/* {
        reverse_proxy 127.0.0.1:8000 {
            flush_interval -1
        }
    }

    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
```

```bash
systemctl reload caddy
journalctl -u caddy -n 20 --no-pager      # look for "certificate obtained"
```

`handle_path` strips `/api`, so the frontend's `https://host/api/advise` reaches the backend as `/advise`. Same origin, so CORS never applies. `flush_interval -1` keeps the chat stream flowing.

## 9. Check

Open `https://agroecoadvisor.duckdns.org/en` and run the full path: Advisor (search Debre Birhan → Erosion & water → Reduce soil loss → results → Why this? → Evidence → Save as PDF), Chat (one question, then "why?"), the microphone, Amharic and Afaan Oromoo, phone width.

Logs while testing: `journalctl -u agro-backend -f`.

## 10. Day-of operations

- Updating code: `cd /srv/agroadvisor && git pull`, then `systemctl restart agro-backend`; for frontend changes also `cd app/frontend && npm run build && systemctl restart agro-frontend`.
- The OpenAI key: set a monthly usage limit in the OpenAI dashboard before the day.
- Optional gate (if the link should not be open to everyone): add inside the Caddy site block
  `basic_auth { validator <hash> }` where `<hash>` comes from `caddy hash-password`. Participants then enter one shared user/password.
- After the validation: DigitalOcean → Droplet → Destroy, so billing stops.
