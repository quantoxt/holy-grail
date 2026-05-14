# Database Design — Supabase

Log every tick, every bot decision, every trade. This data fuels AI training and performance auditing.

---

## Why Supabase?

- PostgreSQL under the hood — proven, fast, query-friendly
- Real-time subscriptions — can push updates to dashboard
- Built-in auth — secure API access
- Free tier generous enough for development
- Python SDK available (`supabase-py`)
- We already know it from previous projects

## Schema Design

### Table: `ticks`
Raw tick data from Deriv. The foundation of everything.

```sql
CREATE TABLE ticks (
  id          BIGSERIAL PRIMARY KEY,
  symbol      TEXT NOT NULL,          -- e.g. 'R_100', '1HZ75V'
  epoch       BIGINT NOT NULL,        -- Unix timestamp (ms)
  tick        DECIMAL(12,6) NOT NULL, -- Tick price
  seq         INTEGER,                -- Tick sequence number
  created_at  TIMESTAMPTZ DEFAULT now(),

  UNIQUE(symbol, epoch)
);

-- Index for fast range queries
CREATE INDEX idx_ticks_symbol_epoch ON ticks(symbol, epoch);
```

### Table: `candles`
Derived OHLC candles built from ticks. Pre-computed to avoid rebuilding on every query.

```sql
CREATE TABLE candles (
  id          BIGSERIAL PRIMARY KEY,
  symbol      TEXT NOT NULL,
  timeframe   TEXT NOT NULL,          -- 'M1', 'M5', 'M15', 'H1', 'H4', 'D1'
  open_time   TIMESTAMPTZ NOT NULL,
  open        DECIMAL(12,6) NOT NULL,
  high        DECIMAL(12,6) NOT NULL,
  low         DECIMAL(12,6) NOT NULL,
  close       DECIMAL(12,6) NOT NULL,
  tick_count  INTEGER,
  created_at  TIMESTAMPTZ DEFAULT now(),

  UNIQUE(symbol, timeframe, open_time)
);
```

### Table: `indicators`
Pre-calculated technical indicators per candle.

```sql
CREATE TABLE indicators (
  id          BIGSERIAL PRIMARY KEY,
  candle_id   BIGINT REFERENCES candles(id),
  symbol      TEXT NOT NULL,
  timeframe   TEXT NOT NULL,
  open_time   TIMESTAMPTZ NOT NULL,
  ema_fast    DECIMAL(12,6),          -- e.g. EMA 9
  ema_slow    DECIMAL(12,6),          -- e.g. EMA 21
  rsi         DECIMAL(8,4),
  bb_upper    DECIMAL(12,6),          -- Bollinger Band upper
  bb_lower    DECIMAL(12,6),          -- Bollinger Band lower
  bb_middle   DECIMAL(12,6),
  atr         DECIMAL(12,6),          -- Average True Range
  adx         DECIMAL(8,4),           -- Trend strength
  created_at  TIMESTAMPTZ DEFAULT now(),

  UNIQUE(symbol, timeframe, open_time)
);
```

### Table: `regimes`
Watcher's regime classifications — audit trail of what the AI saw.

```sql
CREATE TABLE regimes (
  id          BIGSERIAL PRIMARY KEY,
  symbol      TEXT NOT NULL,
  timeframe   TEXT NOT NULL,
  open_time   TIMESTAMPTZ NOT NULL,
  regime      TEXT NOT NULL,          -- 'trending', 'choppy', 'high_volatility'
  confidence  DECIMAL(5,4),           -- 0.0 - 1.0
  features    JSONB,                  -- Raw feature vector that led to classification
  model_version TEXT,                 -- Which model version produced this
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

### Table: `signals`
Soldier's raw signals before execution.

```sql
CREATE TABLE signals (
  id          BIGSERIAL PRIMARY KEY,
  symbol      TEXT NOT NULL,
  timeframe   TEXT NOT NULL,
  signal_time TIMESTAMPTZ NOT NULL,
  direction   TEXT NOT NULL,          -- 'BUY', 'SELL'
  signal_type TEXT NOT NULL,          -- 'ema_cross', 'rsi_extreme', 'bb_touch', etc.
  strength    DECIMAL(5,4),           -- Signal strength 0-1
  indicators  JSONB,                  -- Snapshot of indicators at signal time
  regime      TEXT,                   -- What regime was active
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

### Table: `trades`
Actual executed trades — the money trail.

```sql
CREATE TABLE trades (
  id              BIGSERIAL PRIMARY KEY,
  signal_id       BIGINT REFERENCES signals(id),
  symbol          TEXT NOT NULL,
  contract_type   TEXT NOT NULL,      -- 'CALL', 'PUT', 'DIGITOVER', etc.
  direction       TEXT NOT NULL,      -- 'BUY', 'SELL'
  entry_tick      DECIMAL(12,6),
  exit_tick       DECIMAL(12,6),
  entry_time      TIMESTAMPTZ,
  exit_time       TIMESTAMPTZ,
  stake           DECIMAL(12,4) NOT NULL,
  payout          DECIMAL(12,4),
  profit          DECIMAL(12,4),      -- Can be negative
  lot_multiplier  DECIMAL(4,2) DEFAULT 1.0,
  confidence      DECIMAL(5,4),       -- Sentinel confidence at trade time
  regime          TEXT,               -- Active regime
  duration_ticks  INTEGER,
  result          TEXT,               -- 'win', 'loss', 'sold'
  deriv_contract_id TEXT,             -- Deriv's contract reference
  created_at      TIMESTAMPTZ DEFAULT now()
);
```

### Table: `risk_events`
Sentinel's risk decisions — kill switches, scaling events, alerts.

```sql
CREATE TABLE risk_events (
  id          BIGSERIAL PRIMARY KEY,
  event_type  TEXT NOT NULL,          -- 'kill_switch', 'lot_scale', 'cooldown', 'daily_limit', 'alert'
  reason      TEXT NOT NULL,
  data        JSONB,                  -- Context: drawdown level, streak count, etc.
  lot_before  DECIMAL(4,2),
  lot_after   DECIMAL(4,2),
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

### Table: `bot_sessions`
Track when the bot starts/stops and session-level stats.

```sql
CREATE TABLE bot_sessions (
  id              BIGSERIAL PRIMARY KEY,
  started_at      TIMESTAMPTZ NOT NULL,
  stopped_at      TIMESTAMPTZ,
  mode            TEXT NOT NULL,      -- 'paper', 'demo', 'live'
  symbol          TEXT,
  initial_balance DECIMAL(12,4),
  final_balance   DECIMAL(12,4),
  total_trades    INTEGER DEFAULT 0,
  wins            INTEGER DEFAULT 0,
  losses          INTEGER DEFAULT 0,
  net_profit      DECIMAL(12,4),
  max_drawdown    DECIMAL(8,4),
  notes           TEXT
);
```

## Data Flow

```
Deriv WebSocket
    │
    ▼
ticks table (raw)
    │
    ├──→ candles table (aggregated OHLC)
    │        │
    │        └──→ indicators table (calculated)
    │                 │
    │                 ├──→ signals table (detected)
    │                 │        │
    │                 │        └──→ trades table (executed)
    │                 │
    │                 └──→ regimes table (classified by Watcher)
    │                          │
    │                          └──→ risk_events table (Sentinel decisions)
    │
    └──→ bot_sessions table (lifecycle tracking)
```

## Retention & Performance

- **Ticks:** High volume (~2/sec per symbol). Consider partitioning by month for PostgreSQL performance.
- **Candles:** Low volume (1 per minute max per symbol/timeframe). No issues.
- **Trades:** Very low volume. No issues.
- **Archival strategy:** Move ticks older than 30 days to cold storage or aggregate into hourly stats.

## Open Questions

- Exact indices we're trading (determines tick volume)
- How long to retain raw tick data
- Whether to pre-compute candles in the DB or in Python
- **Supabase free tier limits** — using local Docker Supabase, no cloud limits
- Dashboard metrics TBD — determined by final backend data structure
