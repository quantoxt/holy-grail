# Holy Grail on a Linux VPS (Docker + Wine MT5)

Two containers on one private Docker network:

| service | what | exposure |
|---|---|---|
| `mt5` | `gmag11/metatrader5_vnc:2.3` (Wine + MT5 terminal + KasmVNC desktop) + our RPyC bridge `deploy/mt5/bridge_server.py` on `:18812` | VNC on **127.0.0.1:3000** only; bridge only on the Docker network |
| `bot` | Python 3.12 + CPU torch + Kronos + this repo, `python -m soldier.loop --interval 300` | nothing |

The bot uses the unchanged `providers/mt5.py`. Its import shim falls back to
`providers/mt5_bridge.py` when the Windows-only `MetaTrader5` package is missing.

### Why not the `mt5linux` client and the image's own RPyC server
- The image's `start.sh` installs **unpinned** `mt5linux` at first boot. Today that is
  1.1.x, whose server entrypoint no longer accepts the `-w` flag the image passes.
  The image's port 8001 never comes up. `deploy/mt5/start.sh` replaces the script and
  pins `MetaTrader5==5.0.36` and `rpyc==6.0.2`.
- The `mt5linux` 1.1.x client starts its own Docker container when you construct it.
  0.1.x pins 2021-era dependencies and breaks on `datetime` arguments.
- Both use rpyc *classic* mode, which gives any client a remote Python shell. Our
  bridge exposes an allow-list of MetaTrader5 functions only. Results come back as real
  local namedtuples and numpy arrays, so `._asdict()`, attribute access and
  `pd.DataFrame(rates)` behave like the native package.

## 1. One-time VPS setup (Ubuntu 24.04, as root)

```bash
# Firewall: SSH only. Docker publishes nothing public (VNC is bound to 127.0.0.1).
apt-get update && apt-get install -y ufw git
ufw default deny incoming && ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp   # SHARED BOX: truffl-ping.service answers here (RAW activity check) — do not drop
ufw --force enable

# Docker Engine + compose plugin (official repo)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 4 GB RAM is tight (Wine MT5 ~1 GB + torch/Kronos ~1.5 GB): add swap
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Note: ufw does **not** filter ports that Docker publishes, because Docker writes its own
iptables rules. That is why the compose file never publishes on `0.0.0.0`. Keep it that way.

## 2. Code + secrets

```bash
git clone <repo-url> /opt/holy-grail && cd /opt/holy-grail
cp deploy/env.mt5.example deploy/.env.mt5 && chmod 600 deploy/.env.mt5   # set a VNC password
nano .env && chmod 600 .env
```

The repo-root `.env` needs:

```
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TIMEFRAME=5m
# optional: HF_TOKEN=...   (Kronos weights are public; avoids HF rate limits)
```

Both files are gitignored. Never commit them. MT5 account credentials do **not** go
here. They live in Supabase `mt5_accounts` and are entered from the dashboard.

## 3. Start MT5, then log in once over VNC

```bash
docker compose -f deploy/docker-compose.yml up -d --build mt5
docker compose -f deploy/docker-compose.yml logs -f mt5   # first boot ~5-15 min
```

From your **own machine**, open the tunnel and browse to it:

```bash
ssh -N -L 3000:127.0.0.1:3000 root@128.140.78.209
```

Then open http://localhost:3000 (KasmVNC, user/password from `deploy/.env.mt5`). In
the MT5 window:
1. **File → Login to Trade Account**: The5ers login, password and server. Tick "Save password".
2. Click **Algo Trading** in the toolbar until it is green. Without it, orders fail
   with retcode 10027.
3. Optional: **Tools → Options → Expert Advisors → Allow algorithmic trading**.

The login and AutoTrading state persist in the `mt5_config` volume across restarts.

## 4. Smoke test (read-only, sends no orders)

```bash
docker compose -f deploy/docker-compose.yml build bot
docker compose -f deploy/docker-compose.yml run --rm bot python deploy/smoke_mt5.py EURUSD
```

It must print `ALL PASSED`. It calls `initialize`, `account_info`, `symbols_get`,
`copy_rates_from_pos`, `positions_get` and `history_deals_get` through the shim.

## 5. Run the bot

First set `bot_running=false` on the dashboard. Then:

```bash
docker compose -f deploy/docker-compose.yml up -d bot
docker compose -f deploy/docker-compose.yml logs -f bot
```

Confirm that the heartbeat shows up on the dashboard. Then enable trading and watch the
first order: SL and TP set, size about $25 risk.

## 6. Heartbeat watchdog (host cron)

```bash
crontab -e
* * * * * /usr/bin/python3 /opt/holy-grail/deploy/watchdog.py >> /var/log/holygrail-watchdog.log 2>&1
```

If the newest `account_state.updated_at` is older than 2 min, the watchdog sends a
Telegram alert and restarts the `bot` container. Restarts are limited to one per
10 min, and it sends "recovered" when the heartbeat returns. If Supabase is unreadable,
it only alerts. It uses the stdlib only and reads the repo-root `.env`.

## Operations

```bash
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml restart bot
docker compose -f deploy/docker-compose.yml exec mt5 tail -50 /config/holygrail-start.log
git pull && docker compose -f deploy/docker-compose.yml up -d --build bot   # deploy code
```

- **rpyc versions must match** on both sides: `deploy/Dockerfile` and `RPYC_VERSION`
  in the compose file. If you bump one, bump both, then `docker compose up -d --build`.
- **The MT5 terminal self-updates** inside the volume. Pinning the image does not pin
  MT5. If a terminal update breaks the `MetaTrader5` package, bump `MT5_PY_VERSION`.
- **Restarting `mt5` drops the bridge connection.** The bot's next MT5 call raises,
  and the call after that redials. A call is never retried automatically, because
  `order_send` isn't idempotent.
- **x86_64 only.** The image is amd64.
