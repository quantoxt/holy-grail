"""Deriv Options-API connection helper for the data-puller engine.

Self-contained: mints an OTP (PAT -> authenticated WS URL) and opens the socket.
Credentials are read from the repo-root .env (gitignored).
"""
import json
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
import websockets

# repo root = .../holy-grail  (this file is _engines/data_puller/deriv_ws.py)
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")


def mint_ws_url() -> str:
    """Exchange the PAT for a short-lived authenticated WebSocket URL."""
    base = os.environ["DERIV_API_BASE"]
    acct = os.environ["DERIV_ACCOUNT_ID"]
    token = os.environ["DERIV_API_TOKEN"]
    app_id = os.environ["DERIV_APP_IDENTIFIER"]
    req = urllib.request.Request(f"{base}/accounts/{acct}/otp", method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Deriv-App-ID", app_id)
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())["data"]["url"]


async def connect():
    """Open an authenticated WS. Caller must `await ws.close()`.
    OTPs are short-lived, so a fresh URL is minted per connect (trivial reconnect)."""
    return await websockets.connect(mint_ws_url())
