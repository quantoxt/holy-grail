"""Multi-account MT5 credentials.

Source: data/mt5_accounts.json (gitignored — lives under data/). Switch the
active account by editing "active" in that file, or select per-run with
MT5Provider(account="name") / the loop's --account flag. Add accounts freely.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_FILE = ROOT / "data" / "mt5_accounts.json"


def load() -> dict:
    if ACCOUNTS_FILE.exists():
        return json.loads(ACCOUNTS_FILE.read_text())
    return {"active": None, "accounts": {}}


def list_accounts() -> list:
    return list(load().get("accounts", {}).keys())


def get_account(name: str | None = None) -> dict:
    """Return the named account, or the active one. Raises if none/missing."""
    data = load()
    name = name or data.get("active")
    accounts = data.get("accounts", {})
    if not name or name not in accounts:
        raise ValueError(f"MT5 account {name!r} not found. Available: {list(accounts)}")
    acct = accounts[name]
    for k in ("login", "password", "server"):
        if k not in acct:
            raise ValueError(f"account {name!r} missing '{k}'")
    return acct
