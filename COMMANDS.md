# Holy Grail — Startup Commands

## First-time setup (run once)

```bash
# 1. Python venv + deps
uv venv venv-torch --python 3.12
uv pip install --python venv-torch/bin/python torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python venv-torch/bin/python -r requirements.txt

# 2. Frontend deps
cd frontend && npm install && cd ..

# 3. Supabase (Docker Desktop must be running)
supabase start
PGPASSWORD=postgres psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -f supabase/migrations/001_core_audit.sql
PGPASSWORD=postgres psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -f supabase/migrations/002_grants.sql
PGPASSWORD=postgres psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -f supabase/migrations/003_mt5_accounts.sql

# 4. Copy .env.example to .env and fill in your creds
cp .env.example .env
# Edit .env: set MARKET_MODE, SUPABASE keys, Telegram token, etc.
```

## Daily startup (3 terminals)

```bash
# Terminal 1 — Database (skip if Supabase already running)
supabase start

# Terminal 2 — API backend
./venv-torch/bin/uvicorn api.main:app --port 8000

# Terminal 3 — Frontend dashboard
cd frontend && npm run dev
# Open http://localhost:5173
```

## Start the trading bot

```bash
# Paper mode (testing — no real orders)
./venv-torch/bin/python -m soldier.loop

# Live mode — REAL ORDERS on MT5 demo (Windows only, MT5 terminal must be running)
C:\holy-grail-venv\Scripts\python.exe -m soldier.loop --account demo
```

## Stop everything

```bash
# Stop the bot: Ctrl+C in its terminal
# Stop API: Ctrl+C
# Stop frontend: Ctrl+C
# Stop Supabase:
supabase stop
```

## Useful commands

```bash
# Check bot logs
tail -f data/paper_log.jsonl

# Check API is working
curl localhost:8000/api/status
curl localhost:8000/api/weekly
curl localhost:8000/api/news

# Check Supabase tables
PGPASSWORD=postgres psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -c "SELECT * FROM signals ORDER BY id DESC LIMIT 5;"
PGPASSWORD=postgres psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -c "SELECT * FROM trades ORDER BY id DESC LIMIT 5;"
```
