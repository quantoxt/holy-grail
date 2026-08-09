"""MT5 accounts — Supabase is the ONLY source of truth.

The dashboard writes/activates accounts in the `mt5_accounts` table; the bot reads
the active row (is_active=true) here to log in. If Supabase has no active account
(or is temporarily unreachable), the provider falls back to binding the already-
running terminal session — so the bot keeps trading through a Supabase blip and
never swaps accounts on a network hiccup.
"""
from supabase import create_client

from shared.config import settings

_client = None


def _sb():
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def fetch_active_account() -> dict | None:
    """The active account {name,login,password,server,broker} from Supabase, or None."""
    try:
        r = (_sb().table("mt5_accounts")
             .select("name,login,password,server,broker")
             .eq("is_active", True).limit(1).execute())
        return r.data[0] if r.data else None
    except Exception:
        return None


def fetch_account_by_name(name: str) -> dict | None:
    try:
        r = (_sb().table("mt5_accounts")
             .select("name,login,password,server,broker")
             .eq("name", name).limit(1).execute())
        return r.data[0] if r.data else None
    except Exception:
        return None


def get_account(name: str | None = None) -> dict | None:
    """Return {login,password,server,name} for the active (or named) account.

    None means "no account configured in Supabase" → caller binds the running
    terminal instead. Resilient: a Supabase failure returns None (no raise)."""
    acct = fetch_account_by_name(name) if name else fetch_active_account()
    if not acct:
        return None
    try:
        acct["login"] = int(acct["login"])   # mt5.initialize wants an int login
    except Exception:
        return None
    return acct
