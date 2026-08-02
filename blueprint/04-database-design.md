# Database Design — Supabase (Kronos-Era)

Log every tick, every Kronos prediction, every trade. This data fuels accuracy tracking, risk management, and model retraining.

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

CREATE INDEX idx_ticks_symbol_epoch ON ticks(symbol, epoch);
```

### Table: `candles`
Derived OHLCV candles built from ticks. The direct input to Kronos.

```sql
CREATE TABLE candles (
  id          BIGSERIAL PRIMARY KEY,
  symbol      TEXT NOT NULL,
  timeframe   TEXT NOT NULL,          -- 'M1', 'M5'
  open_time   TIMESTAMPTZ NOT NULL,
  open        DECIMAL(12,6) NOT NULL,
  high        DECIMAL(12,6) NOT NULL,
  low         DECIMAL(12,6) NOT NULL,
  close       DECIMAL(12,6) NOT NULL,
  volume      DECIMAL(18,4) DEFAULT 0, -- Synthetic indices: 0
  amount      DECIMAL(18,4) DEFAULT 0, -- Synthetic indices: 0
  tick_count  INTEGER,
  created_at  TIMESTAMPTZ DEFAULT now(),

  UNIQUE(symbol, timeframe, open_time)
);

CREATE INDEX idx_candles_symbol_tf_time ON candles(symbol, timeframe, open_time);
```

### Table: `kronos_predictions`
**NEW — core table for Kronos-era architecture.** Every Kronos inference result.

```sql
CREATE TABLE kronos_predictions (
  id              BIGSERIAL PRIMARY KEY,
  symbol          TEXT NOT NULL,
  timeframe       TEXT NOT NULL,
  candle_time     TIMESTAMPTZ NOT NULL,       -- Time of the candle that triggered prediction
  model_version   TEXT NOT NULL,               -- e.g. 'kronos-small-v3-deriv-v75-m5'
  tokenizer_version TEXT NOT NULL,              -- e.g. 'tokenizer-v3-deriv-v75-m5'
  lookback        INTEGER NOT NULL,             -- Number of input candles
  pred_len        INTEGER NOT NULL,             -- Number of predicted candles
  sample_count    INTEGER DEFAULT 1,            -- Number of forecast paths averaged
  temperature     DECIMAL(4,2) DEFAULT 1.0,
  top_p           DECIMAL(4,2) DEFAULT 0.9,

  -- Prediction outputs (JSON array of predicted candles)
  predictions     JSONB NOT NULL,               -- [{open, high, low, close, vol, amt}, ...]

  -- Derived metrics (extracted from predictions)
  predicted_close_mean  DECIMAL(12,6),           -- Mean predicted close across pred_len
  predicted_close_std   DECIMAL(12,6),           -- Std dev of predicted closes (variance)
  predicted_direction   TEXT,                     -- 'UP' or 'DOWN'
  predicted_magnitude   DECIMAL(8,6),             -- |predicted_move| as percentage
  predicted_high_max    DECIMAL(12,6),           -- Max predicted high across pred_len
  predicted_low_min     DECIMAL(12,6),           -- Min predicted low across pred_len

  -- Actual outcomes (filled after candle closes)
  actual_close     DECIMAL(12,6),               -- Filled when prediction window elapses
  prediction_error DECIMAL(12,6),               -- |predicted_close_mean - actual_close|
  direction_correct BOOLEAN,                     -- Was predicted direction correct?

  inference_ms     INTEGER,                       -- How long the prediction took (ms)

  created_at       TIMESTAMPTZ DEFAULT now(),

  UNIQUE(symbol, timeframe, candle_time, model_version)
);

CREATE INDEX idx_kp_symbol_tf_time ON kronos_predictions(symbol, timeframe, candle_time);
CREATE INDEX idx_kp_created ON kronos_predictions(created_at);
```

**Why this table matters:** It's the audit trail of everything Kronos sees and predicts. The Watcher's regime classification and the Sentinel's confidence scoring both read from this table. It's also the training data for detecting Kronos drift.

### Table: `regimes`
Watcher's regime classifications — now derived from Kronos predictions, not ML.

```sql
CREATE TABLE regimes (
  id          BIGSERIAL PRIMARY KEY,
  symbol      TEXT NOT NULL,
  timeframe   TEXT NOT NULL,
  candle_time TIMESTAMPTZ NOT NULL,
  regime      TEXT NOT NULL,          -- 'trending', 'normal', 'choppy'
  confidence  DECIMAL(5,4),           -- 0.0 - 1.0

  -- Inputs that led to classification
  prediction_variance  DECIMAL(12,6),  -- Std dev of predicted closes
  rolling_mae          DECIMAL(12,6),  -- Rolling prediction error
  rolling_dir_accuracy DECIMAL(5,4),   -- Rolling directional accuracy

  model_version TEXT,                 -- Kronos model version
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_regimes_symbol_tf_time ON regimes(symbol, timeframe, candle_time);
```

### Table: `signals`
Soldier's trade signals — derived from Kronos predictions.

```sql
CREATE TABLE signals (
  id          BIGSERIAL PRIMARY KEY,
  symbol      TEXT NOT NULL,
  timeframe   TEXT NOT NULL,
  signal_time TIMESTAMPTZ NOT NULL,
  direction   TEXT NOT NULL,          -- 'BUY', 'SELL', 'HOLD'
  signal_type TEXT NOT NULL,          -- 'kronos_prediction' (always this now)
  strength    DECIMAL(5,4),           -- Magnitude of predicted move (0-1)
  kronos_confidence DECIMAL(5,4),    -- From Watcher/Sentinel composite

  -- Kronos prediction context
  predicted_close     DECIMAL(12,6),
  predicted_magnitude DECIMAL(8,6),
  current_close       DECIMAL(12,6),

  -- Filtering
  regime      TEXT,                   -- What regime was active
  regime_filtered BOOLEAN DEFAULT FALSE, -- Was signal suppressed by regime?

  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_signals_symbol_tf_time ON signals(symbol, timeframe, signal_time);
```

### Table: `trades`
Actual executed trades — the money trail.

```sql
CREATE TABLE trades (
  id              BIGSERIAL PRIMARY KEY,
  signal_id       BIGINT REFERENCES signals(id),
  symbol          TEXT NOT NULL,
  contract_type   TEXT NOT NULL,      -- 'CALL', 'PUT', etc.
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
  kronos_pred_id  BIGINT REFERENCES kronos_predictions(id), -- Link to prediction
  duration_ticks  INTEGER,
  result          TEXT,               -- 'win', 'loss', 'sold'
  deriv_contract_id TEXT,             -- Deriv's contract reference
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_trades_symbol_created ON trades(symbol, created_at);
```

### Table: `risk_events`
Sentinel's risk decisions — kill switches, scaling events, alerts.

```sql
CREATE TABLE risk_events (
  id          BIGSERIAL PRIMARY KEY,
  event_type  TEXT NOT NULL,          -- 'kill_switch', 'lot_scale', 'cooldown', 'daily_limit',
                                   -- 'accuracy_drop', 'drift_detected' (Kronos-specific)
  reason      TEXT NOT NULL,
  data        JSONB,                  -- Context: drawdown level, accuracy %, etc.
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
  model_version   TEXT,              -- Kronos model version used
  initial_balance DECIMAL(12,4),
  final_balance   DECIMAL(12,4),
  total_trades    INTEGER DEFAULT 0,
  wins            INTEGER DEFAULT 0,
  losses          INTEGER DEFAULT 0,
  net_profit      DECIMAL(12,4),
  max_drawdown    DECIMAL(8,4),
  kronos_accuracy DECIMAL(5,4),      -- Session-level Kronos directional accuracy
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
    └──→ candles table (aggregated OHLCV)
              │
              └──→ kronos_predictions table (Kronos inference output)
                        │
                        ├──→ regimes table (variance + error → classification)
                        │
                        ├──→ signals table (prediction threshold → BUY/SELL)
                        │        │
                        │        └──→ trades table (executed)
                        │
                        └──→ risk_events table (Sentinel decisions)
    │
    └──→ bot_sessions table (lifecycle tracking)
```

## What Changed vs Original Schema

| Before | After |
|--------|-------|
| `indicators` table (EMA, RSI, BB, ATR, ADX) | **Removed** — Kronos handles internally |
| N/A | `kronos_predictions` table — **new core table** |
| `regimes.features` (JSONB of raw features) | Now `regimes.prediction_variance` + `rolling_mae` + `rolling_dir_accuracy` |
| `regimes.model_version` (HMM version) | Now Kronos model version |
| `trades` no prediction link | `trades.kronos_pred_id` links to prediction |
| `bot_sessions` no model tracking | `bot_sessions.model_version` + `kronos_accuracy` |
| `risk_events.event_type` | Added `accuracy_drop`, `drift_detected` types |

## Retention & Performance

- **Ticks:** High volume (~2/sec per symbol). Monthly partitioning in Postgres. Consider Parquet for cold storage.
- **Candles:** Low volume (1/min per symbol). No issues.
- **Kronos predictions:** One per candle close. Low volume. Index by time for rolling queries.
- **Trades:** Very low volume. No issues.
- **Archival strategy:** Move ticks older than 30 days to Parquet. Keep everything else indefinitely — predictions are valuable for retraining analysis.

## Open Questions

- Exact indices we're trading (determines tick volume)
- Whether to pre-compute candles in the DB or in Python (recommend Python, stream to DB)
- Dashboard metrics (determined by frontend plan — already documented in `_internal/build/frontend-plan.md`)
