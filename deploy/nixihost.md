# Deploy SON on a NixiHost 2GB VPS

NixiHost **Cloud VPS (unmanaged KVM)** with **2GB RAM** can run SON if memory is capped. Prefer **Ubuntu 22.04/24.04**, full root SSH, and a domain A-record pointed at the VPS IP.

## Fit on 2GB

| Service | Approx memory cap |
|---------|-------------------|
| PostGIS | 512MB |
| Redis | 96MB |
| API (1 worker) | 256MB |
| Celery worker (concurrency 1) | 512MB |
| Celery beat | 128MB |
| Caddy | 64MB |

Hourly NRCS ingest is the spike risk — keep worker concurrency at 1. Swap (1–2GB) is recommended.

## 1. Provision

1. Order NixiHost Cloud VPS (2GB+), Ubuntu, root access.
2. In DNS, point `api.yourdomain.com` (or your chosen host) to the VPS public IP.
3. Wait for DNS to resolve before starting Caddy (Let’s Encrypt).

## 2. Server bootstrap (as root)

```bash
apt update && apt upgrade -y
apt install -y ca-certificates curl git ufw fail2ban

# Swap (important on 2GB)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Docker
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

## 3. App install

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/jasonflaherty/Snow-Observations-Network.git son
cd son
git checkout main   # production deploy branch

cp .env.example .env
# edit .env — see below
nano .env
```

Required `.env` additions / changes:

```bash
POSTGRES_PASSWORD=use-a-long-random-password
SON_FREE_KEY=...
SON_RESEARCH_KEY=...
SON_PRO_KEY=...
SON_DOMAIN=api.yourdomain.com
SON_IMAGE=son:prod
```

Keep `DATABASE_URL` / Redis URLs using Docker service names (`postgres`, `redis`) as in `.env.example`.

## 4. Start

```bash
cd /opt/son
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -sS "https://${SON_DOMAIN}/health"
```

## 5. One-time data load

```bash
cd /opt/son
COMPOSE="docker compose -f docker-compose.prod.yml"

# BC is quick (~minutes)
$COMPOSE exec celery-worker \
  python -c "from worker.ingest import ingest_bc_asws_backfill; print(ingest_bc_asws_backfill())"

# NRCS 7-day SNTL — can take a long time on 2GB; run in tmux/screen
$COMPOSE exec celery-worker \
  python -c "from worker.ingest import ingest_nrcs_backfill; print(ingest_nrcs_backfill())"
```

After that, Celery Beat keeps both providers refreshed hourly at `:05` UTC.

## 6. App base URL

Point clients at:

`https://api.yourdomain.com`

Examples:

- `GET /v1/map/stations`
- `GET /v1/stations/SON-CA-BCASWS-2F05P/current`
- Docs: `https://api.yourdomain.com/docs`

## 7. Deploy from GitHub (recommended)

After the first manual install above, push-to-deploy via GitHub Actions.

### One-time: SSH key for Actions

On your **laptop** (not the VPS):

```bash
ssh-keygen -t ed25519 -C "son-github-deploy" -f ~/.ssh/son_vps_deploy -N ""
```

On the **VPS** (as root):

```bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh
echo 'PASTE_CONTENTS_OF_son_vps_deploy.pub_HERE' >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
```

Confirm login works:

```bash
ssh -i ~/.ssh/son_vps_deploy root@YOUR_VPS_IP
```

### One-time: GitHub secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|--------|--------|
| `VPS_HOST` | VPS IPv4 (or hostname) |
| `VPS_USER` | `root` |
| `VPS_SSH_KEY` | Full contents of `~/.ssh/son_vps_deploy` (private key) |
| `VPS_APP_PATH` | `/opt/son` (optional; this is the default) |
| `VPS_PORT` | `22` (optional) |

### How deploys run

- **Automatic:** push to `main` only (markdown-only pushes skipped)
- **Manual:** Actions → **Deploy VPS** → Run workflow (always deploys `main`)

The workflow SSHs in and runs `deploy/deploy.sh`, which:

1. `git fetch` / checkout / `pull --ff-only` on `main`
2. `docker compose -f docker-compose.prod.yml up -d --build`
3. Hits `/health`

`.env` on the VPS is **not** in git and is never overwritten by deploy.

### Manual deploy on the box (same script)

```bash
cd /opt/son
DEPLOY_REF=main ./deploy/deploy.sh
```

## Ops notes

- **Logs:** `docker compose -f docker-compose.prod.yml logs -f api celery-worker`
- **Disk:** raw AWDB/CSV archives live in the `rawdata` volume — prune later if storage is tight
- **CORS:** browser origins via `CORS_ORIGINS` (defaults include GitHub Pages)
- If the box OOMs during NRCS backfill, pause and run with fewer stations first, or upgrade to 4GB

## Checklist

- [ ] Ubuntu VPS + SSH key
- [ ] DNS A record → VPS IP
- [ ] Swap enabled
- [ ] Docker installed
- [ ] `.env` secrets + `SON_DOMAIN`
- [ ] First `compose ... up -d --build`
- [ ] `/health` over HTTPS
- [ ] BC + NRCS backfill
- [ ] GitHub Actions secrets (`VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`)
- [ ] Deploy key in VPS `authorized_keys`
- [ ] Test Actions → Deploy VPS
- [ ] App pointed at the public API URL
