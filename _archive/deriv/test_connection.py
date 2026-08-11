"""
Phase 0 — Step 1: Prove Deriv credentials work (NEW PAT / Options API).

Flow (confirmed against live API):
  1. POST {API_BASE}/accounts/{accountId}/otp  with Bearer PAT + Deriv-App-ID
     -> returns {data:{url:"wss://.../ws/demo?otp=..."}}
  2. Connect to that URL (OTP authenticates the session; no separate authorize).
  3. Speak the WS message protocol to read balance + stream ticks.

Run:  ./venv/bin/python -m research.test_connection
"""

import asyncio
import json
import os
import sys
import urllib.request

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception: pass

from dotenv import load_dotenv
import websockets

SYMBOL = "R_75"          # Volatility 75 Index — Phase 0 target
READ_WINDOW = 2.0        # max silence (s) before assuming a request is done replying
MAX_REPLIES = 4          # cap — streaming requests (ticks) would loop forever otherwise


def mint_ws_url() -> str:
    """Exchange the PAT for a short-lived authenticated WebSocket URL."""
    base = os.environ["DERIV_API_BASE"]
    acct = os.environ["DERIV_ACCOUNT_ID"]
    token = os.environ["DERIV_API_TOKEN"]
    app_id = os.environ["DERIV_APP_IDENTIFIER"]

    url = f"{base}/accounts/{acct}/otp"
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Deriv-App-ID", app_id)
    with urllib.request.urlopen(req, timeout=12) as r:
        data = json.loads(r.read())["data"]
    return data["url"]


async def probe(ws, label, request):
    """Send one request and collect all replies for READ_WINDOW seconds."""
    req = dict(request)
    req.setdefault("req_id", abs(hash(label)) % 100000)
    print(f"\n→ {label}: {json.dumps(request)}")
    await ws.send(json.dumps(req))
    count = 0
    while count < MAX_REPLIES:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=READ_WINDOW)
        except asyncio.TimeoutError:
            break
        count += 1
        print(f"   ← {raw[:400]}")
    if count == 0:
        print("   (no reply)")


async def main() -> int:
    load_dotenv()
    token = os.environ.get("DERIV_API_TOKEN")
    if not token:
        print("✗ Missing DERIV_API_TOKEN in .env"); return 1

    print("→ Minting authenticated WS URL via OTP …")
    ws_url = mint_ws_url()
    # otp is a secret — mask it in logs
    masked = ws_url.split("?otp=")[0] + "?otp=***"
    print(f"✓ Got WS URL: {masked}")

    print("→ Connecting (OTP authenticates the session) …")
    async with websockets.connect(ws_url) as ws:
        print("✓ Connected")

        # Empirically discover the message schema. Try legacy-shaped requests
        # first (conceptual API often carries over), then adapt from replies.
        await probe(ws, "ping", {"ping": 1})
        await probe(ws, "balance", {"balance": 1})
        await probe(ws, "active_symbols", {"active_symbols": "brief"})
        await probe(ws, "ticks_history",
                    {"ticks_history": SYMBOL, "count": 5, "end": "latest", "style": "ticks"})
        await probe(ws, "ticks_stream", {"ticks": SYMBOL})

    print("\n✅ Connection test complete — reviewed replies above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
