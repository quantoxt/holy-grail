# Holy Grail — Frontend Build Plan

**Date:** 2026-06-25  
**Stack:** Vue 3 (SPA) + Tailwind CSS 4 + shadcn-vue + FastAPI  
**Served:** Vue static build from FastAPI, single process  

---

## Architecture

```
holy-grail/
├── sidx/                    # Python bot (existing)
│   ├── bot/                 # Soldier
│   ├── research/            # Backtesting
│   ├── monitor/             # Current basic dashboard (replace)
│   └── api/                 # NEW — FastAPI backend
│       ├── __init__.py
│       ├── main.py          # FastAPI app, serves Vue static + REST + WS
│       ├── routes/
│       │   ├── status.py    # Bot status, regime, confidence
│       │   ├── trades.py    # Trade history, open trades
│       │   ├── regime.py    # Watcher data
│       │   ├── risk.py      # Sentinel data
│       │   └── control.py   # Start/stop/pause/config
│       └── ws/
│           └── handler.py   # WebSocket — push ticks, trades, regime changes
│
├── frontend/                # Vue SPA (NEW)
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.ts
│   │   ├── router/
│   │   ├── stores/          # Pinia
│   │   ├── composables/     # API hooks, WS connection
│   │   ├── components/
│   │   ├── views/
│   │   └── assets/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── Dockerfile               # Multi-stage: build Vue, bundle with Python
└── docker-compose.yml
```

### Build & Deploy Flow

```
1. Develop:
   - Terminal A: python -m sidx.bot.run_paper (bot running)
   - Terminal B: cd frontend && pnpm dev (Vite dev server, proxies /api to FastAPI)

2. Production build:
   - cd frontend && pnpm build  →  frontend/dist/
   - FastAPI serves dist/ as static files
   - uvicorn sidx.api.main:app — single process

3. VPS deploy:
   - Docker container with Python + built Vue files
   - One process, one port
```

---

## API Contract

### REST Endpoints

| Method | Path | Returns |
|--------|------|---------|
| `GET` | `/api/status` | Bot state, uptime, mode (paper/demo/live) |
| `GET` | `/api/balance` | Account balance, daily P&L |
| `GET` | `/api/trades` | Trade history (paginated, filterable) |
| `GET` | `/api/trades/open` | Currently open trades |
| `GET` | `/api/regime` | Current regime + confidence + features |
| `GET` | `/api/regime/history` | Regime history timeline |
| `GET` | `/api/risk` | Sentinel state — lot multiplier, drawdown, kill switch |
| `GET` | `/api/risk/events` | Risk events log (kill switches, scaling) |
| `GET` | `/api/performance` | Per-signal-type stats, win rates |
| `GET` | `/api/config` | Current bot config (strategy + risk params) |
| `PATCH` | `/api/config` | Update config (hot reload) |
| `POST` | `/api/control/start` | Start bot |
| `POST` | `/api/control/stop` | Stop bot |
| `POST` | `/api/control/pause` | Pause trading (stay connected) |
| `GET` | `/api/symbols` | Available Deriv symbols + contract types |

### WebSocket Events (server → client)

| Event | Payload | Trigger |
|-------|---------|---------|
| `tick` | `{ symbol, price, epoch }` | Every incoming tick |
| `candle_close` | `{ symbol, timeframe, ohlc }` | On candle close |
| `signal` | `{ direction, type, strength, indicators }` | New signal detected |
| `trade_open` | `{ trade_id, direction, entry, stake, confidence, regime }` | Trade executed |
| `trade_close` | `{ trade_id, exit, profit, result, duration }` | Trade settled |
| `regime_change` | `{ regime, confidence, features, model_version }` | Regime reclassified |
| `risk_event` | `{ type, reason, lot_before, lot_after }` | Sentinel action |
| `bot_status` | `{ state, uptime, trades_today, daily_pnl }` | Periodic (every 5s) |

### WebSocket Events (client → server)

| Event | Payload | Purpose |
|-------|---------|---------|
| `subscribe` | `{ channels: ["tick", "trade", "regime"] }` | Subscribe to event types |
| `unsubscribe` | `{ channels: ["tick"] }` | Stop receiving ticks (save bandwidth) |

---

## Views & Layout

### Layout Shell

```
┌─────────────────────────────────────────────────┐
│  Holy Grail                    [● Live] [$842]  │  ← Top bar: status, mode, balance
├──────┬──────────────────────────────────────────┤
│      │                                          │
│ Dash │            Main Content                  │
│ board│                                          │
│      │                                          │
│ Trades                                          │
│      │                                          │
│ Regime                                          │
│      │                                          │
│ Risk                                            │
│      │                                          │
│ Config                                          │
│      │                                          │
│ Settngs                                         │
│      │                                          │
└──────┴──────────────────────────────────────────┘
```

- Sidebar: dark, icon + label, collapsible
- Top bar: persistent — bot status dot, P&L counter, current regime badge
- Mobile: sidebar collapses to hamburger menu, top bar stays

---

### 1. Dashboard (default view)

The command center. Everything at a glance.

```
┌─────────────────────┬─────────────────────┐
│  ACCOUNT BALANCE    │  TODAY'S P&L        │
│  $10,842.50         │  +$182.30 (1.7%)    │
│  ↗ +1.8% this week  │  14 trades, 9W/5L   │
└─────────────────────┴─────────────────────┘

┌─────────────────────┬─────────────────────┐
│  CURRENT REGIME     │  SENTINEL STATE     │
│  ● TRENDING         │  Confidence: 78%    │
│  ADX: 32.1          │  Lot multiplier: 2x │
│  2h 14m in regime   │  Drawdown: 3.2%     │
└─────────────────────┴─────────────────────┘

┌─────────────────────────────────────────────┐
│  LIVE PRICE CHART                            │
│  [V75 candlestick chart with indicators      │
│   overlay — EMA fast/slow, BB, RSI panel]    │
│  [Signal markers: ▲ BUY  ▼ SELL]             │
│  [Regime background: green=trend, gray=chop] │
└─────────────────────────────────────────────┘

┌─────────────────────┬─────────────────────┐
│  OPEN TRADES        │  RECENT SIGNALS     │
│  CALL V75  +$12.30  │  ▲ EMA Cross  0.91  │
│  PUT V100 -$3.20    │  ▼ RSI Extreme 0.74 │
│                     │  — BB Touch (filtered: choppy) │
└─────────────────────┴─────────────────────┘
```

**Components:**
- `StatCard` — reusable metric card (label, value, delta, icon)
- `PriceChart` — candlestick + indicator overlays (use lightweight-charts or chart.js)
- `RegimeBadge` — colored pill showing current regime
- `TradesList` — compact open trades table
- `SignalFeed` — scrolling list of recent signals with filter reasons

---

### 2. Trades

Full trade management view.

```
┌──────────────────────────────────────────────────────────┐
│  FILTERS: [All Regimes ▼] [All Types ▼] [Today ▼]       │
├──────────────────────────────────────────────────────────┤
│  ID  Symbol  Dir  Entry   Exit    Result  P&L    Regime  │
│  45  R_75    CALL 1024.3  1031.2  WIN    +$8.20 Trend    │
│  44  R_100   PUT  5821.7  5819.1  WIN    +$8.20 Trend    │
│  43  R_75    CALL 1019.8  1018.1  LOSS   -$10.0 Chop     │
│  ...                                                      │
├──────────────────────────────────────────────────────────┤
│  Pagination: < 1 2 3 ... 12 >                            │
└──────────────────────────────────────────────────────────┘

Summary (below table):
  Total: 287 trades | Win rate: 61.3% | Avg win: $8.40 | Avg loss: -$9.80
  Best regime: Trending (68% win) | Worst: Choppy (41% win)
```

**Components:**
- `TradesTable` — sortable, paginated, with regime + signal type columns
- `TradeDetail` — expandable row showing full indicator snapshot at entry/exit
- `PerformanceSummary` — aggregate stats with filter context
- `TradesChart` — P&L curve over time (cumulative)

---

### 3. Regime (Watcher)

Deep dive into what the AI sees.

```
┌─────────────────────────────────────────────────────────┐
│  CURRENT REGIME: ● TRENDING (confidence: 87%)           │
│  Model: hmm_v3 | In regime for 2h 14m                   │
├─────────────────────────────────────────────────────────┤
│  FEATURE VALUES                                         │
│  ATR:           0.45    ████████░░  (high)              │
│  ADX:          32.1    ██████████░  (strong trend)      │
│  RSI variance:  12.3   ███░░░░░░░░  (low)               │
│  Entropy:       0.72   ██████░░░░░  (moderate)          │
│  BB width:     tight   ██░░░░░░░░░  (squeeze)           │
│  Autocorr:     0.34    ███████░░░░  (significant)       │
├─────────────────────────────────────────────────────────┤
│  REGIME TIMELINE (last 24h)                             │
│  [Horizontal bar chart:                                 │
│   green = trending, gray = choppy, amber = high vol     │
│   with transition markers]                              │
├─────────────────────────────────────────────────────────┤
│  REGIME STATS                                           │
│  Trending:  68% of time | 65% win rate                  │
│  Choppy:    22% of time | 38% win rate (bot paused)     │
│  High Vol:  10% of time | 52% win rate                  │
└─────────────────────────────────────────────────────────┘
```

**Components:**
- `RegimeGauge` — circular gauge showing confidence %
- `FeatureBars` — horizontal bar chart of feature values vs percentile
- `RegimeTimeline` — 24h horizontal strip showing regime transitions
- `RegimeStats` — performance breakdown per regime

---

### 4. Risk (Sentinel)

Risk management cockpit.

```
┌─────────────────────┬─────────────────────┐
│  DRAWDOWN GAUGE     │  KILL SWITCH        │
│  ████░░░░░░ 3.2%    │  ● ARMED            │
│  Limit: 15%         │  Triggers:          │
│  Safe               │  □ Daily loss < 3%  │
│                     │  □ Streak < 5       │
│                     │  □ Drawdown < 15%   │
├─────────────────────┴─────────────────────┤
│  CONFIDENCE → LOT SCALING                │
│  Current: 78% → 2x multiplier            │
│  [Stair-step visualization:              │
│   <50% = 0x | 50-70% = 1x | 70-85% = 2x │
│   85-90% = 3x | 90%+ = 5x]               │
├───────────────────────────────────────────┤
│  RISK EVENTS LOG                          │
│  14:32  Lot scaled 1x → 2x (confidence up)│
│  13:15  Cooldown ended (streak broke)     │
│  12:40  ⚠ Kill switch: 3 consecutive loss │
│  09:00  Session started                   │
├───────────────────────────────────────────┤
│  DAILY/WEEKLY P&L CHART                   │
│  [Bar chart: green/red days]              │
└───────────────────────────────────────────┘
```

**Components:**
- `DrawdownGauge` — semicircular gauge, green→amber→red zones
- `KillSwitchPanel` — status + trigger checklist
- `LotScaleViz` — stair-step chart mapping confidence to multiplier
- `RiskEventLog` — timeline of Sentinel decisions
- `PnLChart` — daily/weekly cumulative P&L bars

---

### 5. Config

Bot configuration editor.

```
┌─────────────────────────────────────────────┐
│  STRATEGY                                   │
│  EMA Fast:      [20    ]                    │
│  EMA Slow:      [50    ]                    │
│  RSI Period:    [14    ]                    │
│  RSI Buy Max:   [35.0  ]                    │
│  RSI Sell Min:  [65.0  ]                    │
│  ...                                        │
├─────────────────────────────────────────────┤
│  RISK                                       │
│  Risk per trade:  [0.35 %]                  │
│  Max trades/day:  [8     ]                  │
│  Max daily loss:  [2.0   %]                 │
│  Max consec loss:  [3    ]                  │
│  Cooldown:        [12    ] min              │
│  Session:         [08:00 - 20:00 UTC]       │
├─────────────────────────────────────────────┤
│  EXECUTION                                  │
│  Mode:           ( ) Paper  (•) Demo  ( ) Live │
│  Symbol:         [R_75  ▼]                  │
│  Contract dur:   [10    ] min               │
│  Stake:          [$1.00 ]                   │
├─────────────────────────────────────────────┤
│  [Save & Apply]  [Reset]  [Validate Only]   │
└─────────────────────────────────────────────┘
```

**Components:**
- `ConfigForm` — grouped form sections with validation
- `ModeToggle` — radio group for paper/demo/live (confirmation modal for live)
- `SaveBar` — sticky bottom bar with save/reset/validate actions

---

### 6. Settings (bot infrastructure)

```
┌─────────────────────────────────────────────┐
│  DERIV CONNECTION                           │
│  API Token:      [••••••••••]  [Test]       │
│  App ID:         [1089  ]                   │
│  WebSocket URL:  [wss://ws.derivws.com/...] │
│  Status:         ● Connected (23ms latency) │
├─────────────────────────────────────────────┤
│  TELEGRAM                                   │
│  Enabled:       [✓]                         │
│  Bot Token:     [••••••••••]                │
│  Chat ID:       [••••••••••]                │
│  [Send Test Message]                        │
├─────────────────────────────────────────────┤
│  DATABASE                                   │
│  Supabase URL:  [http://localhost:5432]     │
│  Status:        ● Connected                 │
│  Tick storage:  1.2M rows (342MB)           │
│  [Archive old ticks]                        │
└─────────────────────────────────────────────┘
```

---

## Component Library

### Tech Choices

| Need | Choice | Why |
|------|--------|-----|
| UI framework | Vue 3 + Composition API | Standard, well-known |
| Styling | Tailwind CSS 4 | Rapid, consistent, dark mode trivial |
| Components | shadcn-vue | Copy-paste, fully customizable, looks clean |
| State | Pinia | Official Vue store, TypeScript-first |
| Routing | Vue Router | Standard |
| Charts | lightweight-charts (TradingView) | Candlesticks done right, tiny bundle |
| Data tables | TanStack Table (via shadcn-vue) | Sorting, filtering, pagination built-in |
| HTTP | Native fetch + composables | No axios needed, keep it lean |
| WebSocket | Native WebSocket + composable | Reconnect logic in a composable |
| Icons | Lucide (via shadcn-vue) | Clean, consistent, tree-shakeable |
| Notifications | vue-sonner (shadcn-vue) | Toast notifications for trade events |

### Color System (Tailwind)

```
Dark mode (default):
- bg:        zinc-950
- card:      zinc-900
- border:    zinc-800
- text:      zinc-100
- muted:     zinc-500

Accent (semantic):
- profit:    emerald-500
- loss:      red-500
- trending:  emerald-500
- choppy:    zinc-500
- highvol:   amber-500
- danger:    red-600
- info:      blue-500
```

### Reusable Components to Build

| Component | Props | Used In |
|-----------|-------|---------|
| `StatCard` | label, value, delta, icon, accent | Dashboard |
| `RegimeBadge` | regime, confidence | Top bar, dashboard, trades |
| `PriceChart` | symbol, timeframe, signals, regime_bands | Dashboard |
| `ConfidenceGauge` | value (0-100) | Dashboard, risk |
| `DrawdownGauge` | current, max | Risk |
| `LotScaleViz` | confidence, multiplier | Risk |
| `TradesTable` | trades, filters | Trades |
| `SignalFeed` | signals, max_items | Dashboard |
| `RegimeTimeline` | history[] | Regime |
| `FeatureBars` | features{} | Regime |
| `EventLog` | events[], types[] | Risk |
| `PnLChart` | data[], period | Dashboard, trades, risk |
| `ConfigForm` | sections, values | Config |
| `BotStatusDot` | state | Top bar, sidebar |
| `ModeBadge` | mode (paper/demo/live) | Top bar |

---

## Real-time Strategy

### WebSocket composable

```typescript
// composables/useBotWebSocket.ts
export function useBotWebSocket() {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const ticks = ref<Tick[]>([])
  const openTrades = ref<Trade[]>([])
  const currentRegime = ref<Regime | null>(null)

  // Auto-reconnect with backoff
  // Route events to appropriate Pinia stores
  // Throttle tick updates (max 10/sec to UI, even if 2/sec from Deriv)

  return { connected, ticks, openTrades, currentRegime }
}
```

### Update throttling
- **Ticks:** Buffer and flush to chart every 100ms (10fps). Raw 2/sec from Deriv is fine.
- **Trade events:** Immediate — these are rare and important.
- **Regime changes:** Immediate with toast notification.
- **Bot status:** Poll every 5s via REST fallback (in case WS drops).

### Pinia stores

```
stores/
├── bot.ts          # status, mode, uptime, config
├── trades.ts       # open trades, trade history, pagination
├── regime.ts       # current regime, history, features
├── risk.ts         # sentinel state, drawdown, lot multiplier, events
├── market.ts       # live ticks, candles, current price
└── notifications.ts # toast queue
```

---

## Build Phases

### Phase F1: Skeleton (Day 1-2)
- Vue project setup (Vite + Tailwind + shadcn-vue)
- Layout shell (sidebar + topbar)
- Pinia stores (empty stubs)
- WebSocket composable with reconnect
- Router with all views (placeholder content)
- Dark mode default

### Phase F2: Dashboard (Day 3-4)
- StatCards (balance, P&L, regime, sentinel)
- Live price chart (lightweight-charts)
- Signal feed
- Open trades list
- Real-time WS data flowing into stores

### Phase F3: Trades View (Day 5)
- Full trades table with filters
- Trade detail expansion
- Performance summary
- P&L curve chart

### Phase F4: Regime View (Day 6)
- Current regime gauge
- Feature bars
- Regime timeline
- Regime stats breakdown

### Phase F5: Risk View (Day 7)
- Drawdown gauge
- Kill switch panel
- Lot scale visualization
- Risk event log
- Daily P&L chart

### Phase F6: Config + Settings (Day 8)
- Config form with validation
- Mode toggle (paper/demo/live with confirmation)
- Deriv connection settings
- Telegram settings
- Database status

### Phase F7: FastAPI Integration (Day 9-10)
- All REST endpoints wired
- WebSocket events flowing
- Vue build served from FastAPI
- Docker multi-stage build
- Single `docker-compose up`

---

## FastAPI Backend (sidx/api/)

```
sidx/api/
├── __init__.py
├── main.py              # FastAPI app + static serving + WS endpoint
├── deps.py              # Dependency injection (bot instance, db)
├── routes/
│   ├── __init__.py
│   ├── status.py        # GET /api/status, /api/balance
│   ├── trades.py        # GET /api/trades, /api/trades/open
│   ├── regime.py        # GET /api/regime, /api/regime/history
│   ├── risk.py          # GET /api/risk, /api/risk/events
│   ├── performance.py   # GET /api/performance
│   ├── config.py        # GET/PATCH /api/config
│   └── control.py       # POST /api/control/*
└── ws/
    ├── __init__.py
    └── handler.py       # WS connection manager, event broadcaster
```

### main.py (sketch)

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Holy Grail API")

# Routes
app.include_router(status.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
# ... etc

# WebSocket
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    # broadcast events from bot → connected clients

# Serve Vue SPA (production)
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="spa")
```

---

## Vite Config (proxy for dev)

```typescript
// frontend/vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true }
    }
  },
  build: {
    outDir: 'dist',
  }
})
```

During dev: Vite on `:5173`, FastAPI on `:8000`, proxy handles routing.
During prod: FastAPI serves everything on one port.

---

## Docker

```dockerfile
# Stage 1: Build Vue
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/ .
RUN corepack enable && pnpm install && pnpm build

# Stage 2: Python runtime
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY sidx/ ./sidx/
COPY --from=frontend /app/frontend/dist ./frontend/dist
CMD ["uvicorn", "sidx.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

One container. One port. Done.
