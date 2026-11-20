"""Telegram alerts — best-effort notification for trade + risk events.

No-op if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured in .env.
Called from the loop on trade open/close + kill switch.

Multi-chat: send_telegram defaults to the owner chat (TELEGRAM_CHAT_ID) but
accepts an explicit chat_id so alerts fan out to command-center subscribers.
get_updates() powers the inbound command poller (shared/telegram_commands.py).
"""
import asyncio
import json
import urllib.parse
import urllib.request

from shared.config import settings


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


def _post(method: str, payload: dict, timeout: int = 10):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(_api(method), data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _send_sync(message: str, reply_to: int | None = None,
               chat_id: str | int | None = None) -> int | None:
    """POST sendMessage; returns the new message's id (used to thread close
    alerts as replies to their open alert) or None on any failure."""
    token = settings.telegram_bot_token
    chat = chat_id or settings.telegram_chat_id
    if not token or not chat:
        return None
    payload = {"chat_id": chat, "text": message, "parse_mode": "Markdown"}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        body = _post("sendMessage", payload)
        return body.get("result", {}).get("message_id")
    except Exception:
        return None


async def send_telegram(message: str, reply_to: int | None = None,
                        chat_id: str | int | None = None) -> int | None:
    """Send a Telegram message (async, non-blocking). Returns its message id."""
    return await asyncio.to_thread(_send_sync, message, reply_to, chat_id)


def get_updates(offset: int | None = None, timeout: int = 30) -> list:
    """Long-poll Bot API getUpdates (single-flight: only ONE poller may run —
    the bot container owns it). Returns the raw update list, [] on transient
    network failure or when not configured. HTTP errors (e.g. 409 = another
    getUpdates consumer is stealing updates) RAISE so the caller can log them —
    swallowing them made a dead poller invisible."""
    import urllib.error
    if not settings.telegram_bot_token:
        return []
    params = {"timeout": timeout, "allowed_updates": json.dumps(["message"])}
    if offset is not None:
        params["offset"] = offset
    url = _api("getUpdates") + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout + 10) as resp:
            body = json.loads(resp.read().decode())
        if not body.get("ok"):
            raise RuntimeError(f"getUpdates not ok: {str(body)[:120]}")
        return body.get("result", [])
    except urllib.error.HTTPError:
        raise  # caller logs the status code (409 = conflicting poller)
    except Exception:
        return []
