# Configuration Reference — Every Knob

There are two kinds of settings, and they live in different places:

1. **Settings** (`shared/config.py`, from `.env`) — immutable, fixed at boot. Model paths,
   credentials, the Kronos inference parameters, execution-guard thresholds. **Needs a restart
   to change.**
2. **RuntimeConfig** (`shared/runtime_config.py`, stored in Supabase `bot_config`) — the live,
   dashboard-adjustable params. **Hot-reloaded every ~5s — no restart.**

This doc lists both, what each does, the default, and how to change it.

---

## RuntimeConfig — the live knobs (dashboard Config page, or the RPC)

These are the ones you'll touch. Change them from the dashboard (Config → edit → Save &
Apply), or via the merge RPC (see `vps-troubleshooting.md` §8). The bot picks them up within
~5 seconds.

### Goal & account framing
| Field | Default | What it does |
|---|---|---|
| `baseline_equity` | 50 | The week's reference balance. Floor = `baseline − max_weekly_drawdown`; ceiling = `baseline + weekly_goal`. |
| `weekly_goal` | 14 | $ profit target per week. Reaching it (in equity or realized+floating PnL) → close all + stop for the week. |
| `withdraw_profit_weekly` | true | Log weekly profit as "withdrawn" at the Monday reset (anti-compounding). |

> The ceiling is `baseline + weekly_goal`. Set `baseline` to the account's real starting
> balance (e.g. 500) so the floor/ceiling sit sensibly around it. If `baseline` is 500 but
> the live account is $61, the equity-floor kill fires immediately (61 < 400 floor) — that's
> the "config doesn't match the account" trap.

### Per-trade risk
| Field | Default | What it does |
|---|---|---|
| `max_risk_per_trade` | 1 | Reference $ risk (drives Thursday boost + daily-budget calc). **Not** the real risk — min-lot is. |
| `risk_cap_pct` | 0.03 | **The real per-trade ceiling:** skip if actual $-at-SL > `risk_cap_pct × equity`. The blowup guard. |
| `sl_multiplier` | 2.0 | SL distance = `sl_multiplier × |predicted_move|`. Wider = fewer noise stops, bigger $-at-SL. |
| `max_open_positions` | 2 | Concurrent trades cap. |

### Per-trade exit (profit-lock)
| Field | Default | What it does |
|---|---|---|
| `profit_lock_target` | 5 | Floating-$ at which the SL starts ratcheting into profit. |
| `profit_lock_min` | 2 | Minimum $ profit to lock once trailing engages. |
| `profit_lock_fraction` | 0.5 | Lock `max(profit_lock_min, peak_profit × fraction)`. |

### Guardrails (kill switches)
| Field | Default | What it does |
|---|---|---|
| `max_daily_loss` | 3 | Realized daily loss → close all + cool off. |
| `max_weekly_drawdown` | 10 | Floor = `baseline − this`. Equity at/below → stop. |

### Thursday aggression
| Field | Default | What it does |
|---|---|---|
| `thursday_aggression` | true | Enable last-day risk boost. |
| `thursday_threshold` | 7 | Only boost if `weekly_pnl` below this. |
| `thursday_risk` | 1.5 | Boosted risk amount. |
| `min_confidence_for_boost` | 0.9 | Only boost on A-grade signals. |

### Filters
| Field | Default | What it does |
|---|---|---|
| `correlation_filter` | true | If a correlated pair signals together, take only the stronger. |
| `correlated_pairs` | `[["XAUUSD","XAGUSD"]]` | Pairs treated as correlated. |
| `news_blackout_enabled` | true | Pause around high-impact news. |
| `news_blackout_pre_min` / `post_min` | 30 / 15 | Minutes before/after to pause. |

### Symbols & control
| Field | Default | What it does |
|---|---|---|
| `active_symbols` | `["XAUUSD","XAGUSD","EURUSD","GBPUSD"]` | What to scan. The bot skips any the broker doesn't offer. |
| `bot_running` | true | Master start/stop. |
| `trading_paused` | false | Pause (stay connected, no new trades). |

---

## Settings — the boot-time knobs (`.env` / `shared/config.py`)

Change these in `.env` (gitignored) or `shared/config.py` defaults. **Needs a restart.**

### Market & model
| Field | Default | What it does |
|---|---|---|
| `TIMEFRAME` | 5m | Candle timeframe. |
| `kronos_model` | `NeoQuasar/Kronos-small` | The pre-trained model. |
| `kronos_tokenizer` | `NeoQuasar/Kronos-Tokenizer-base` | Tokenizer. |
| `KRONOS_PATH` | `model/Kronos` | Local path to Kronos code. |
| `lookback` | 512 | Context window (candles fed to Kronos). |
| `pred_len` | 24 | **The edge horizon** — 24 × 5m = 2h. |
| `sample_count` | 1 | Kronos samples. Higher = less noisy but slower (CPU). |
| `confidence_threshold` | 0.003 | `|move| ≥ 0.3%` to trade (vs HOLD). |

### Execution guards
| Field | Default | What it does |
|---|---|---|
| `spread_max_of_move` | 0.25 | Skip if spread > 25% of `|predicted_move|` (eats the edge). |
| `snr_min` | 1.0 | Skip if `|move| / horizon-noise < 1` (signal lost in chop). |
| `breakeven_lock` | true | Enable the breakeven-lock trail tier. |
| `breakeven_lock_mult` | 1.0 | Favorable move (× `|move|`) before locking breakeven. |

### Credentials (`.env`, never commit)
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (bot+API only, **never** Vercel),
`SUPABASE_ANON_KEY` (public, dashboard), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
MT5 creds (also in Supabase `mt5_accounts`).

---

## How to change things

| Want to change… | How | Restart? |
|---|---|---|
| Goal, caps, symbols, risk, start/stop | Dashboard Config → Save, **or** RPC patch | No (5s) |
| `.env` value (model, creds, timeframe) | edit `.env` on the VPS | Yes |
| `shared/config.py` default (a guard threshold) | edit + `scp` to VPS | Yes |
| Code (any `.py`) | edit + `scp` + restart | Yes |

> RPC patch example (no restart): see `vps-troubleshooting.md` §8b. A plain Supabase PATCH
> would **replace the whole config** — always use the `update_bot_config` merge RPC.
