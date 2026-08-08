"""Telegram alerts — best-effort notification for trade + risk events.

No-op if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured in .env.
Called from the loop on trade open + kill switch.
"""
import asyncio
import json
import urllib.request

from shared.config import settings


def _send_sync(message: str):
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


async def send_telegram(message: str):
    """Send a Telegram message (async, non-blocking)."""
    await asyncio.to_thread(_send_sync, message)
