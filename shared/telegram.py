"""Telegram alerts — best-effort notification for trade + risk events.

No-op if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured in .env.
Called from the loop on trade open/close + kill switch.
"""
import asyncio
import json
import urllib.request

from shared.config import settings


def _send_sync(message: str, reply_to: int | None = None) -> int | None:
    """POST sendMessage; returns the new message's id (used to thread close
    alerts as replies to their open alert) or None on any failure."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            return body.get("result", {}).get("message_id")
    except Exception:
        return None


async def send_telegram(message: str, reply_to: int | None = None) -> int | None:
    """Send a Telegram message (async, non-blocking). Returns its message id."""
    return await asyncio.to_thread(_send_sync, message, reply_to)
