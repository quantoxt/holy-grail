"""Central config for the Holy Grail bot. Loads from the gitignored .env.

Single broker: all instruments (forex, metals, crypto-CFD) trade through one
logged-in MT5 account. `market_mode` is a vestigial label (still logged to DB
columns) — provider selection no longer branches on it. Traded symbols come
from RuntimeConfig.active_symbols (dashboard-adjustable), NOT from env.
Pre-trained Kronos (zero-shot, no fine-tune) is the prediction engine; the
validated edge is at h=24 on confident signals.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _env(key, default=""):
    return os.environ.get(key, default)


def _envf(key, default=0.0):
    v = os.environ.get(key)
    return float(v) if v is not None else default


def _envi(key, default=0):
    v = os.environ.get(key)
    return int(v) if v is not None else default


@dataclass
class Settings:
    # --- market routing ---
    market_mode: str = field(default_factory=lambda: _env("MARKET_MODE", "forex"))  # vestigial label (logged to DB)
    timeframe: str = field(default_factory=lambda: _env("TIMEFRAME", "5m"))

    # --- Kronos (pre-trained, zero-shot) ---
    kronos_model: str = "NeoQuasar/Kronos-small"
    kronos_tokenizer: str = "NeoQuasar/Kronos-Tokenizer-base"
    kronos_path: str = field(default_factory=lambda: _env("KRONOS_PATH", str(ROOT / "model" / "Kronos")))
    lookback: int = 512
    pred_len: int = 24          # the validated directional edge (h=24)
    sample_count: int = 1       # CPU-safe on the VPS
    confidence_threshold: float = 0.003   # |predicted_move| >= 0.3% to trade (55% slice)

    # --- execution guards (spread / volatility / trailing) ---
    spread_max_of_move: float = 0.25   # skip if spread > 25% of |predicted_move| (eats the edge)
    snr_min: float = 1.0               # skip if |move| / horizon-noise < 1 (signal lost in noise)
    breakeven_lock: bool = True        # once +1× move in favor, slide safety SL to breakeven
    breakeven_lock_mult: float = 1.0   # how much favorable move (× |predicted_move|) before locking

    # --- risk (Sentinel) ---
    base_stake: float = field(default_factory=lambda: _envf("BASE_STAKE", 1.0))
    max_stake_mult: float = 5.0
    daily_loss_limit: float = field(default_factory=lambda: _envf("DAILY_LOSS_LIMIT", 0.05))   # 5%
    max_consecutive_losses: int = 5

    # --- provider credentials (MT5 only — single broker) ---
    mt5_login: int = field(default_factory=lambda: _envi("MT5_LOGIN"))
    mt5_password: str = field(default_factory=lambda: _env("MT5_PASSWORD"))
    mt5_server: str = field(default_factory=lambda: _env("MT5_SERVER"))

    # --- infra ---
    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_service_role_key: str = field(default_factory=lambda: _env("SUPABASE_SERVICE_ROLE_KEY"))
    supabase_anon_key: str = field(default_factory=lambda: _env("SUPABASE_ANON_KEY"))
    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))

    paper: bool = field(default_factory=lambda: _env("PAPER", "1") == "1")  # demo until explicitly live


settings = Settings()
