"""Holy Grail trading loop — LIVE mode, multi-symbol best-opportunity selection.

Scans ALL active symbols each cycle, ranks by confidence, opens positions on
the best opportunities (respecting max_open_positions + correlation filter).
Telegram alerts on every trade open + close (with P&L + balance). No paper mode.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
from shared.config import settings  # noqa: E402
from shared.runtime_config import runtime  # noqa: E402
from shared.database import db  # noqa: E402
from shared.telegram import send_telegram  # noqa: E402
from providers import get_provider  # noqa: E402
from soldier.signal import SignalEngine  # noqa: E402
from watcher.regime import Watcher  # noqa: E402
from sentinel.risk import sentinel as sentinel_inst  # noqa: E402

LOG = ROOT / "data" / "paper_log.jsonl"


class Trader:
    def __init__(self, account=None):
        self.provider = get_provider(account=account)
        self.engine = SignalEngine()
        self.watcher = Watcher()
        self.sentinel = sentinel_inst
        self.open: dict = {}
        self.candle_idx = 0
        LOG.parent.mkdir(parents=True, exist_ok=True)

    def log(self, **kw):
        kw["ts"] = datetime.now(timezone.utc).isoformat()
        with open(LOG, "a") as f:
            f.write(json.dumps(kw) + "\n")
        print("[" + kw.get("type", "") + "] " +
              " ".join(f"{k}={v}" for k, v in kw.items() if k not in ("ts", "type")))

    async def get_balance(self) -> float:
        try:
            return (await self.provider.get_balance()).get("balance", 50.0)
        except Exception:
            return 50.0

    async def run_cycle(self):
        """One time step: resolve old → scan all → rank → open best.
        (Account hot-swap is handled in the 5s telemetry task, not here.)"""
        self.candle_idx += 1

        # Phase 1: Resolve matured positions
        await self._resolve_positions()

        # Phase 2: Kill switch check
        bal = await self.get_balance()
        killed, kreason = self.sentinel.check_kill(
            bal, len(self.open), symbols=runtime.active_symbols)
        if killed:
            self.log(type="KILL", reason=kreason, bal=bal, weekly_pnl=f"${self.sentinel.weekly_pnl:.2f}")
            try:
                db.log_risk_event("kill_switch", kreason, {"balance": bal})
            except Exception:
                pass
            return

        # Phase 3: Scan ALL symbols for signals
        signals = {}
        for sym in runtime.active_symbols:
            try:
                # Graceful skip: ignore active symbols the logged-in broker doesn't offer
                # (e.g. BTCUSD on a forex-only account) — no crash, no failed orders.
                if hasattr(self.provider, "is_offered") and not self.provider.is_offered(sym):
                    self.log(type="SKIP", symbol=sym, reason="not offered by broker")
                    continue
                candles = await self.provider.get_candles(sym, settings.timeframe, settings.lookback + 5)
                sig = self.engine.get_signal(candles)
                signals[sym] = sig
                try:
                    db.log_signal(sym, settings.timeframe, sig["direction"],
                                  sig["confidence"], sig["predicted_move"],
                                  sig["current_close"], sig["predicted_close"], sig["horizon"])
                except Exception:
                    pass
            except Exception as e:
                self.log(type="ERROR", symbol=sym, msg=str(e))

        # Phase 4: Rank by confidence (descending), filter HOLDs
        tradeable = {sym: sig for sym, sig in signals.items()
                     if sig["direction"] != "HOLD" and sym not in self.open}
        ranked = sorted(tradeable.items(), key=lambda x: abs(x[1]["predicted_move"]), reverse=True)

        # Phase 5: Open positions (best first, up to max_open_positions)
        open_slots = runtime.max_open_positions - len(self.open)
        opened_syms = set()

        for sym, sig in ranked:
            if open_slots <= 0:
                break

            # Correlation filter: skip if a correlated pair is already opened this cycle
            if runtime.correlation_filter:
                skip = False
                for pair in runtime.correlated_pairs:
                    if sym in pair and any(s in pair for s in opened_syms):
                        skip = True
                        self.log(type="FILTER", msg=f"correlation: {sym} skipped (pair already opened)")
                        break
                if skip:
                    continue

            # Compute risk + lot
            candle_date = datetime.now(timezone.utc).date()
            self.sentinel.check_time_resets(candle_date)
            risk = self.sentinel.risk_amount(sig["confidence"], candle_date)
            spec = await self.provider.get_symbol_info(sym)
            entry = sig["current_close"]
            lot = self.sentinel.lot_size(
                risk, entry, sig["sl_price"],
                spec["contract_size"], spec["volume_min"], spec["volume_step"])

            if lot < spec["volume_min"] or risk <= 0:
                self.log(type="SKIP", symbol=sym, reason=f"lot={lot}<min={spec['volume_min']}")
                continue

            # Execute
            ticket = None
            try:
                result = await self.provider.open_position(sym, sig["direction"], lot, sl=sig["sl_price"])
                ticket = result.get("id")
                if not result.get("ok", True) and not ticket:
                    self.log(type="ERROR", msg=f"order rejected: {result}")
                    continue
            except Exception as e:
                self.log(type="ERROR", msg=f"open failed {sym}: {e}")
                continue

            self.open[sym] = {
                "direction": sig["direction"], "entry_price": entry,
                "entry_idx": self.candle_idx, "lot": lot,
                "contract_size": spec["contract_size"],
                "ticket": ticket, "trade_id": None, "sl_price": sig["sl_price"],
            }
            try:
                self.open[sym]["trade_id"] = db.log_trade_open(
                    sym, sig["direction"], entry, risk, sig["confidence"],
                    settings.pred_len, paper=False)
            except Exception:
                pass

            open_slots -= 1
            opened_syms.add(sym)
            action = f"LIVE OPEN {sym} {sig['direction']} lot={lot} risk=${risk:.2f}"
            self.log(type="OPEN", symbol=sym, dir=sig["direction"], lot=lot,
                     risk=risk, conf=f"{sig['confidence']:.2f}", action=action)

            # Telegram: trade opened
            try:
                await send_telegram(
                    f"📡 OPEN {sym} {sig['direction']}\n"
                    f"Lot: {lot} | Risk: ${risk:.2f}\n"
                    f"Confidence: {sig['confidence']:.0%} | Entry: {entry:.2f}")
            except Exception:
                pass

        # Log summary
        holds = {sym: sig for sym, sig in signals.items() if sig["direction"] == "HOLD"}
        self.log(type="CYCLE", scanned=len(signals), tradeable=len(tradeable),
                 opened=len(opened_syms), open_total=len(self.open),
                 holds=len(holds), bal=bal,
                 weekly_pnl=f"${self.sentinel.weekly_pnl:.2f}")

    async def _resolve_positions(self):
        """Close positions whose h=pred_len horizon has elapsed."""
        for sym, pos in list(self.open.items()):
            if self.candle_idx - pos["entry_idx"] < settings.pred_len:
                continue

            # Get current price for P&L
            try:
                candles = await self.provider.get_candles(sym, settings.timeframe, 5)
                cur = float(candles["close"].iloc[-1])
            except Exception:
                continue

            direction_sign = 1 if pos["direction"] == "BUY" else -1
            price_diff = (cur - pos["entry_price"]) * direction_sign
            pnl = price_diff * pos["lot"] * pos["contract_size"]
            correct = price_diff > 0

            # Close real position
            if pos.get("ticket"):
                try:
                    await self.provider.close_position(pos["ticket"])
                except Exception as e:
                    self.log(type="ERROR", msg=f"close failed {sym}: {e}")

            # Update tracking
            self.sentinel.on_trade_closed(pnl, correct)
            self.watcher.record_resolution(correct)

            bal = await self.get_balance()
            result_str = "WIN ✅" if correct else "LOSS ❌"
            self.log(type="CLOSE", symbol=sym, dir=pos["direction"],
                     entry=round(pos["entry_price"], 2), exit=round(cur, 2),
                     pnl=f"${pnl:+.2f}", result=result_str,
                     bal=bal, weekly_pnl=f"${self.sentinel.weekly_pnl:.2f}",
                     consec_losses=self.sentinel.consecutive_losses)

            try:
                db.log_trade_close(pos.get("trade_id"), cur, pnl,
                                   "win" if correct else "loss")
            except Exception:
                pass

            # Telegram: trade closed with P&L + balance
            try:
                await send_telegram(
                    f"{'🟢' if correct else '🔴'} CLOSE {sym} {pos['direction']}\n"
                    f"P&L: ${pnl:+.2f} ({result_str})\n"
                    f"Balance: ${bal:.2f}\n"
                    f"Weekly P&L: ${self.sentinel.weekly_pnl:.2f} / ${runtime.weekly_goal:.2f}")
            except Exception:
                pass

            del self.open[sym]

    async def _telemetry(self):
        """Near-realtime account heartbeat, independent of the (slow) trade cycle.
        Every ~5s: pull latest dashboard config (hot-reload), check for an MT5
        account switch (Supabase is the source of truth), then publish live
        balance / equity / floating PnL / positions / symbols / news blackout."""
        sym_refresh_every = 6   # refresh broker symbol list every 6th tick (~30s)
        tick = 0
        while True:
            try:
                await asyncio.sleep(5)
                tick += 1
                runtime.refresh()                                   # hot-reload dashboard edits
                await self._maybe_switch_account()                  # dashboard-driven swap
                acct = await self.provider.account_summary()
                positions = await self.provider.get_open_positions()
                floating = round(sum(p.get("profit", 0) for p in positions), 2)
                syms = self.provider.discover_symbols(force=(tick % sym_refresh_every == 0))
                # news blackout — published so the dashboard can show a banner
                blackout, reason = (False, "")
                try:
                    from shared.news import is_blackout
                    blackout, reason = is_blackout(runtime.active_symbols,
                                                   runtime.news_blackout_pre_min,
                                                   runtime.news_blackout_post_min)
                except Exception:
                    pass
                db.upsert_account_state(
                    acct["login"], acct["broker"], acct["balance"], acct["equity"],
                    acct["currency"], floating, positions, syms,
                    news_blackout=blackout, news_reason=reason)
            except Exception as e:
                self.log(type="TELEMETRY_ERR", msg=str(e))

    async def _maybe_switch_account(self):
        """If the dashboard changed the active MT5 account (Supabase mt5_accounts),
        hot-swap the terminal connection. No-op when nothing changed or Supabase
        is unreachable (never swap on a blip)."""
        if not (hasattr(self.provider, "check_account_switch")
                and self.provider.check_account_switch()):
            return
        try:
            self.provider.reconnect()
            self.log(type="SWITCH", msg=f"switched to {self.provider.account_name}")
            try:
                await send_telegram(f"🔄 MT5 account switched to {self.provider.account_name}")
            except Exception:
                pass
        except Exception as e:
            self.log(type="ERROR", msg=f"account switch failed: {e}")

    async def run(self, cycles=None, interval_sec=300):
        runtime.refresh()   # boot from the dashboard's last-saved config, not code defaults
        c = 0
        telemetry = asyncio.create_task(self._telemetry())
        try:
            while cycles is None or c < cycles:
                if not runtime.bot_running:
                    self.log(type="STATUS", msg="bot_stopped via dashboard")
                    await asyncio.sleep(10)
                    continue
                await self.run_cycle()
                c += 1
                if (cycles is None or c < cycles) and interval_sec > 0:
                    await asyncio.sleep(interval_sec)
        finally:
            telemetry.cancel()
            try:
                mt5_shutdown = getattr(self.provider, "shutdown", None)
                if mt5_shutdown:
                    mt5_shutdown()
            except Exception:
                pass


def main():
    # Under pythonw (the scheduled-task launcher) there is no console, so stdout/stderr
    # are None and prints would be lost. Mirror them to the log files so debugging works
    # with no visible window. (When launched via the .bat redirect, these are already set.)
    try:
        if sys.stdout is None:
            sys.stdout = open(ROOT / "data" / "bot.log", "a", buffering=1)
        if sys.stderr is None:
            sys.stderr = open(ROOT / "data" / "bot.err", "a", buffering=1)
    except Exception:
        pass

    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=int, default=None)
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--account", default=None)
    args = p.parse_args()
    trader = Trader(account=args.account)
    print(f"Holy Grail | LIVE | symbols={runtime.active_symbols} "
          f"tf={settings.timeframe} goal=${runtime.weekly_goal}", flush=True)
    asyncio.run(trader.run(cycles=args.cycles, interval_sec=args.interval))
if __name__ == "__main__":
    main()
