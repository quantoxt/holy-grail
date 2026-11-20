"""Telegram command center — inbound half of the bot.

The bot historically only SENT messages (shared/telegram.py). This module
POLLS getUpdates (long-poll, single-flight from the bot container — the VPS
exposes no public ingress, so webhooks are not an option) and answers the
BotFather menu commands: /start /subscribe /unsubscribe /signals /status
/brief /check /help /pause /resume /settings /history + owner-only
/subscribers /broadcast.

Access model: only SUBSCRIBED chats (telegram_subscribers.status='active',
owner included) get answers; strangers are told to /subscribe. Anyone with
the bot username can subscribe — keep the username private. Every command is
logged (type=TGCMD) for audit. Handlers never raise.
"""
import asyncio
import time
from datetime import datetime, timezone

from shared import telegram as tg
from shared.config import settings
from shared.database import db
from shared.runtime_config import runtime


def parse_command(text: str):
    """'/check XAUUSD@HolyGrailBot extra' -> ('check', 'XAUUSD extra')."""
    if not text or not text.strip().startswith("/"):
        return None, ""
    first = text.strip().split()[0].split("@")[0].lower()
    args = text.strip()[len(text.strip().split()[0]):].strip()
    return first.lstrip("/"), args


def _money(v, sign=False) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    s = f"{abs(n):,.2f}"
    return f"{'−' if n < 0 else ('+' if sign and n > 0 else '')}${s}"


class CommandCenter:
    """Owns the getUpdates poll loop. Needs the live Trader for provider +
    engine access (/brief, /check). All handler I/O is best-effort."""

    def __init__(self, trader):
        self.trader = trader
        self.offset = None
        self.check_cooldowns: dict = {}  # chat_id -> epoch of last /check

    # ---- entry point (spawned from Trader.run alongside telemetry) ----
    async def run(self):
        self._log("command poller started")
        try:
            if settings.telegram_chat_id:
                db.ensure_owner_subscriber(settings.telegram_chat_id)
        except Exception:
            pass
        # Discard stale backlog so a restart doesn't replay yesterday's commands.
        try:
            backlog = await asyncio.to_thread(tg.get_updates, None, 5)
            if backlog:
                self.offset = max(u.get("update_id", 0) for u in backlog) + 1
                self._log(f"skipped {len(backlog)} stale update(s)")
        except Exception as e:
            self._log(f"backlog check failed: {type(e).__name__} {self._code(e)}")
        fails = 0
        while True:
            try:
                updates = await asyncio.to_thread(tg.get_updates, self.offset, 30)
                fails = 0
            except Exception as e:
                fails += 1
                # Log every HTTP error (409 = another poller stealing updates)
                # and every 10th transient failure — silence hid a dead poller.
                import urllib.error
                if isinstance(e, urllib.error.HTTPError) or fails % 10 == 1:
                    self._log(f"getUpdates failed ({fails}x): {type(e).__name__} {self._code(e)}")
                await asyncio.sleep(5)
                continue
            for u in updates or []:
                try:
                    self.offset = max(self.offset or 0, u.get("update_id", 0) + 1)
                    await self._route(u)
                except Exception:
                    continue

    def _log(self, msg: str):
        try:
            self.trader.log(type="TGCMD", msg=msg)
        except Exception:
            pass

    @staticmethod
    def _code(e) -> str:
        return str(getattr(e, "code", "") or getattr(e, "args", [""])[0])[:80]

    async def _route(self, update: dict):
        msg = update.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if not chat_id or not text.startswith("/"):
            return  # plain chatter is ignored — no noise in the alert channel
        cmd, args = parse_command(text)
        sender = (msg.get("from") or {})
        name = (sender.get("first_name") or chat.get("title") or "").strip()[:60]
        try:
            self.trader.log(type="TGCMD", cmd=cmd, chat=chat_id, args=args[:60])
        except Exception:
            pass
        handler = getattr(self, f"cmd_{cmd}", None)
        if handler is None:
            await self._reply(chat_id, f"Unknown command /{cmd}. Try /help.")
            return
        try:
            await handler(chat_id, args, name)
        except Exception as e:
            try:
                await self._reply(chat_id, "Hmm, that failed. Try again in a bit.")
                self.trader.log(type="TGCMD_ERR", cmd=cmd, msg=str(e)[:120])
            except Exception:
                pass

    # ---- helpers ----
    def _is_owner(self, chat_id) -> bool:
        return str(chat_id) == str(settings.telegram_chat_id)

    async def _reply(self, chat_id, text: str):
        try:
            await tg.send_telegram(text, chat_id=chat_id)
        except Exception:
            pass

    def _subscriber(self, chat_id):
        try:
            return db.get_subscriber(chat_id)
        except Exception:
            return None

    async def _require_sub(self, chat_id, name) -> bool:
        """Gate: subscribed (or owner) chats only. Auto-heals the owner row."""
        if self._is_owner(chat_id):
            try:
                db.ensure_owner_subscriber(chat_id)
            except Exception:
                pass
            return True
        sub = self._subscriber(chat_id)
        if sub and sub.get("status") == "active":
            return True
        await self._reply(chat_id, "You're not subscribed to this bot. Send /subscribe to opt in.")
        return False

    # ---- public commands ----
    async def cmd_start(self, chat_id, args, name):
        try:
            db.subscribe_chat(chat_id, name)
        except Exception:
            pass
        await self.cmd_help(chat_id, args, name)

    async def cmd_subscribe(self, chat_id, args, name):
        try:
            db.subscribe_chat(chat_id, name)
        except Exception:
            await self._reply(chat_id, "Couldn't save that — try again in a bit.")
            return
        await self._reply(chat_id, "Subscribed. You'll get signal + trade alerts here. /unsubscribe anytime, /pause to mute.")

    async def cmd_unsubscribe(self, chat_id, args, name):
        try:
            db.unsubscribe_chat(chat_id)
        except Exception:
            pass
        await self._reply(chat_id, "Unsubscribed — no more alerts here. /subscribe to rejoin.")

    async def cmd_help(self, chat_id, args, name):
        await self._reply(chat_id,
            "Holy Grail commands:\n"
            "/signals — latest signal alerts\n"
            "/status — bot, account + positions\n"
            "/brief — latest setup per instrument\n"
            "/check SYMBOL — analyze one instrument now\n"
            "/history — last 5 closed trades\n"
            "/pause / /resume — mute / unmute alerts (trading untouched)\n"
            "/settings — your notification settings\n"
            "/unsubscribe — stop all alerts")

    async def cmd_pause(self, chat_id, args, name):
        if not await self._require_sub(chat_id, name):
            return
        try:
            sub = self._subscriber(chat_id)
            if not sub:
                db.subscribe_chat(chat_id, name)
            db.set_muted(chat_id, True)
        except Exception:
            pass
        await self._reply(chat_id, "Notifications paused. Trading is untouched. /resume to unmute.")

    async def cmd_resume(self, chat_id, args, name):
        try:
            sub = self._subscriber(chat_id)
            if not sub:
                db.subscribe_chat(chat_id, name)
            else:
                db.set_muted(chat_id, False)
        except Exception:
            pass
        await self._reply(chat_id, "Notifications on. You'll get alerts again.")

    async def cmd_settings(self, chat_id, args, name):
        if not await self._require_sub(chat_id, name):
            return
        sub = self._subscriber(chat_id) or {}
        cfg = {}
        try:
            runtime.refresh()
            cfg = runtime.snapshot()
        except Exception:
            pass
        await self._reply(chat_id,
            "Your settings:\n"
            f"Subscribed: {'yes' if (sub.get('status') == 'active' or self._is_owner(chat_id)) else 'no'}\n"
            f"Muted: {'yes (/resume)' if sub.get('muted') else 'no'}\n"
            f"Signal Mode: {'on' if cfg.get('signals_enabled', True) else 'off'}\n"
            f"Alert cooldown: {cfg.get('signal_cooldown_min', 120)} min\n"
            f"Min confidence: {float(cfg.get('min_confidence', 0.5)):.0%}")

    async def cmd_status(self, chat_id, args, name):
        if not await self._require_sub(chat_id, name):
            return
        try:
            snap = db.status_snapshot()
        except Exception:
            await self._reply(chat_id, "Couldn't reach the database right now.")
            return
        acct, cfg = snap.get("account") or {}, snap.get("config") or {}
        equity = acct.get("equity")
        try:
            runtime.refresh()
            live = runtime.snapshot()
        except Exception:
            live = cfg
        state = "stopped"
        if live.get("bot_running"):
            if live.get("trading_paused"):
                state = "paused (signals on)"
            elif live.get("signals_enabled", True):
                state = "signal mode (alerts only, no trades)"
            else:
                state = "running (live trading)"
        positions = acct.get("open_positions") or []
        lines = [
            f"Bot: {state} | Mode: {live.get('account_mode', '?')}",
            f"Equity: {_money(equity)} (bal {_money(acct.get('balance'))}"
            + (f", floating {_money(acct.get('floating_pnl'), True)}" if acct.get("floating_pnl") else "") + ")",
            f"Weekly: {_money(acct.get('weekly_pnl'), True)} / {_money(live.get('weekly_goal', 0))} goal"
            if acct.get("weekly_pnl") is not None else "Weekly: n/a",
            f"Open: {len(positions)} position(s)",
        ]
        for p in positions[:5]:
            if isinstance(p, dict):
                lines.append(f"· {p.get('symbol')} {p.get('type', '')} "
                             f"{_money(p.get('profit'), True)}")
        await self._reply(chat_id, "\n".join(lines))

    async def cmd_signals(self, chat_id, args, name):
        if not await self._require_sub(chat_id, name):
            return
        try:
            snap = db.status_snapshot()
        except Exception:
            await self._reply(chat_id, "Couldn't reach the database right now.")
            return
        rows = [s for s in (snap.get("signals") or []) if s.get("direction") in ("BUY", "SELL")]
        if not rows:
            await self._reply(chat_id, "No signal alerts yet. They appear here when a setup clears every trade gate.")
            return
        lines = ["Latest signal alerts:"]
        for s in rows[:5]:
            try:
                when = datetime.fromisoformat(str(s["signal_time"])).strftime("%m-%d %H:%M")
            except Exception:
                when = "?"
            emoji = "🟢" if s.get("direction") == "BUY" else "🔴"
            conf = s.get("confidence")
            conf_txt = f"{float(conf):.0%}" if conf is not None else "?"
            entry = s.get("entry_price")
            entry_txt = f"{float(entry):.2f}" if entry is not None else "?"
            sent = "" if s.get("telegram_sent", True) else " (not sent)"
            lines.append(f"{emoji} {s.get('symbol')} {s.get('direction')} @ {entry_txt} ({conf_txt}, {when}){sent}")
        await self._reply(chat_id, "\n".join(lines))

    async def cmd_history(self, chat_id, args, name):
        if not await self._require_sub(chat_id, name):
            return
        try:
            snap = db.status_snapshot()
        except Exception:
            await self._reply(chat_id, "Couldn't reach the database right now.")
            return
        rows = [t for t in (snap.get("trades") or []) if t.get("result") in ("win", "loss")]
        if not rows:
            await self._reply(chat_id, "No closed trades yet.")
            return
        lines = ["Last closed trades:"]
        for t in rows[:5]:
            emoji = "🟢" if t.get("result") == "win" else "🔴"
            lines.append(f"{emoji} {t.get('symbol')} {t.get('direction')} "
                         f"{_money(t.get('pnl'), True)} ({t.get('result')})")
        await self._reply(chat_id, "\n".join(lines))

    async def cmd_brief(self, chat_id, args, name):
        if not await self._require_sub(chat_id, name):
            return
        try:
            rows = db.client.table("signals").select(
                "symbol,direction,confidence,predicted_move,signal_time") \
                .order("signal_time", desc=True).limit(60).execute().data or []
        except Exception:
            await self._reply(chat_id, "Couldn't reach the database right now.")
            return
        latest = {}
        for r in rows:
            if r.get("symbol") not in latest:
                latest[r["symbol"]] = r
        if not latest:
            await self._reply(chat_id, "No scans yet. The bot scans every 5 minutes.")
            return
        lines = ["Market overview (latest scan per instrument):"]
        for sym in sorted(latest):
            r = latest[sym]
            d = r.get("direction")
            emoji = "🟢" if d == "BUY" else ("🔴" if d == "SELL" else "⏸️")
            try:
                move = f"{float(r.get('predicted_move')):+.2%}"
            except (TypeError, ValueError):
                move = "?"
            lines.append(f"{emoji} {sym}: {d} ({move})")
        await self._reply(chat_id, "\n".join(lines))

    async def cmd_check(self, chat_id, args, name):
        if not await self._require_sub(chat_id, name):
            return
        sym = (args or "").strip().upper().split()[0] if args else ""
        if not sym:
            await self._reply(chat_id, "Usage: /check SYMBOL (e.g. /check XAUUSD).")
            return
        now = time.time()
        if now - self.check_cooldowns.get(chat_id, 0) < 120:
            await self._reply(chat_id, "Easy — one live check every 2 minutes per chat.")
            return
        self.check_cooldowns[chat_id] = now
        try:
            offered = self.trader.provider.is_offered(sym)
        except Exception:
            offered = True
        if not offered:
            await self._reply(chat_id, f"{sym} isn't offered by the connected broker.")
            return
        await self._reply(chat_id, f"Analyzing {sym} — a few seconds…")
        try:
            candles = await self.trader.provider.get_candles(
                sym, settings.timeframe, settings.lookback + 5)
            # Same worker-thread + lock path as the scan cycle: the loop stays
            # free and concurrent inferences can't race inside the model.
            sig = await asyncio.to_thread(self.trader._infer, candles, sym)
        except Exception as e:
            await self._reply(chat_id, f"Couldn't analyze {sym} right now.")
            try:
                self.trader.log(type="TGCMD_ERR", cmd="check", msg=str(e)[:120])
            except Exception:
                pass
            return
        d = sig.get("direction", "HOLD")
        emoji = "🟢" if d == "BUY" else ("🔴" if d == "SELL" else "⏸️")
        verdict = []
        try:
            runtime.refresh()
            if d == "HOLD":
                verdict.append("no setup (below entry threshold)")
            else:
                if sig.get("confidence", 0) < runtime.min_confidence:
                    verdict.append(f"below confidence bar ({runtime.min_confidence:.0%})")
                if sig.get("snr", 99) < settings.snr_min:
                    verdict.append("lost in noise (low SNR)")
                spread = self.trader.provider.get_spread(sym)
                entry = sig.get("current_close") or 0
                if entry and spread / entry > settings.spread_max_of_move * abs(sig.get("predicted_move") or 0):
                    verdict.append("spread eats the edge")
                if not verdict:
                    verdict.append("clears every gate — would alert")
        except Exception:
            pass
        sl = sig.get("sl_price")
        body = (f"{emoji} {sym} {d} ({settings.timeframe})\n"
                f"Price: {sig.get('current_close'):.2f} → predicted {sig.get('predicted_close'):.2f}\n"
                f"Move: {sig.get('predicted_move'):+.2%} | Confidence: {sig.get('confidence'):.0%} | SNR: {sig.get('snr'):.2f}\n")
        if sl:
            body += f"SL: {sl:.2f}\n"
        body += f"Verdict: {'; '.join(verdict)}"
        await self._reply(chat_id, body)

    # ---- owner-only ----
    async def cmd_subscribers(self, chat_id, args, name):
        if not self._is_owner(chat_id):
            await self._reply(chat_id, "Owner only.")
            return
        try:
            rows = db.all_subscribers()
        except Exception:
            await self._reply(chat_id, "Couldn't reach the database right now.")
            return
        if not rows:
            rows = []
        lines = [f"Subscribers ({len(rows)}):"]
        for r in rows[:30]:
            flag = "👑" if r.get("is_owner") else ("🔇" if r.get("muted") else "✅")
            lines.append(f"{flag} {r.get('chat_id')} {r.get('status')} {r.get('note') or ''}".rstrip())
        await self._reply(chat_id, "\n".join(lines))

    async def cmd_broadcast(self, chat_id, args, name):
        if not self._is_owner(chat_id):
            await self._reply(chat_id, "Owner only.")
            return
        if not args:
            await self._reply(chat_id, "Usage: /broadcast Your message here")
            return
        try:
            subs = db.active_subscribers()
        except Exception:
            subs = []
        sent = 0
        for s in subs or []:
            try:
                await tg.send_telegram(f"📣 {args}", chat_id=s.get("chat_id"))
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                continue
        await self._reply(chat_id, f"Broadcast sent to {sent} chat(s).")
