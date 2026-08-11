"""Holy Grail trading loop — LIVE mode, multi-symbol best-opportunity selection.

Scans ALL active symbols each cycle, ranks by confidence, opens positions on
the best opportunities (respecting max_open_positions + correlation filter).
Telegram alerts on every trade open + close (with P&L + balance). No paper mode.

RISK (post 2026-08-10 overnight review):
  * Lot is min-lot-bound (0.01). We accept that BUT cap each trade's actual
    $-at-SL at risk_cap_pct of equity — refuse suicide, don't refuse trade.
  * Goal-aware exit: once LIVE EQUITY reaches baseline+weekly_goal, close ALL
    positions and stop for the week (bank the goal). Per-trade, once floating
    profit >= profit_lock_target, ratchet SL into a profit-lock so a winner can
    never become a loss. h=24 remains the max hold.
  * On startup we RECONCILE self.open from the broker's real positions (our
    magic) so a restart/crash never orphans an open trade.
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
CYCLE_SEC = 300   # --interval default; used to age reconciled positions


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
        # JSONL audit file — utf-8 (json.dumps escapes non-ascii anyway, but be explicit).
        try:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(kw) + "\n")
        except Exception:
            pass
        # Console mirror. NEVER let a logging call crash the bot (the overnight death
        # was a UnicodeEncodeError printing the '❌' emoji to a cp1252 Windows stream).
        try:
            msg = "[" + kw.get("type", "") + "] " + \
                  " ".join(f"{k}={v}" for k, v in kw.items() if k not in ("ts", "type"))
            print(msg, flush=True)
        except Exception:
            pass

    async def get_balance(self) -> float:
        try:
            return (await self.provider.get_balance()).get("balance", 50.0)
        except Exception:
            return 50.0

    async def _balance_equity_floating(self) -> tuple[float, float, float]:
        """Live (balance, equity, floating_pnl). Tolerant — never raises."""
        try:
            b = await self.provider.get_balance()
            bal = b.get("balance", 50.0)
            eq = b.get("equity", bal)
            positions = await self.provider.get_open_positions()
            floating = round(sum(p.get("profit", 0) for p in positions), 2)
            return bal, eq, floating
        except Exception:
            return 50.0, 50.0, 0.0

    async def _reconcile_positions(self):
        """Rebuild self.open from the broker's ACTUAL open positions (our magic
        only). Without this, a restart/crash orphans every open trade — the bot
        couldn't see, trail, or close them. Best-effort; never raises."""
        try:
            positions = await self.provider.get_open_positions()
        except Exception as e:
            self.log(type="RECONCILE_ERR", msg=str(e))
            return
        for p in positions:
            sym = p["symbol"]
            if sym in self.open:
                continue
            try:
                spec = await self.provider.get_symbol_info(sym)
            except Exception:
                spec = {"contract_size": 1.0, "volume_min": 0.01, "volume_step": 0.01}
            entry = p["entry"]
            sl = p.get("sl") or 0.0
            # estimate entry cycle index from the broker open time so the
            # h=pred_len horizon exit still fires for recovered positions
            opened_at = p.get("time")
            elapsed = (datetime.now(timezone.utc).timestamp() - float(opened_at)) if opened_at else 0.0
            cycles_elapsed = max(0, int(elapsed // CYCLE_SEC))
            # recover `move` from current SL vs entry (sl_multiplier×|move|×entry ≈ |entry-sl|)
            move = (abs(entry - sl) / (entry * runtime.sl_multiplier)
                    if (entry and sl and runtime.sl_multiplier) else 0.0)
            self.open[sym] = {
                "direction": p["type"], "entry_price": entry,
                "entry_idx": self.candle_idx - cycles_elapsed,
                "lot": p["volume"], "contract_size": spec["contract_size"],
                "ticket": p["ticket"], "trade_id": None,
                "sl_price": sl or None, "move": move,
                "peak_profit": max(0.0, p.get("profit", 0.0)),
                "recovered": True,
            }
            self.log(type="RECONCILE", symbol=sym, dir=p["type"], lot=p["volume"],
                     entry=entry, sl=sl, msg="recovered open position")
        if self.open:
            self.log(type="RECONCILE", msg=f"recovered {len(self.open)} open position(s) from broker")

    async def run_cycle(self):
        """One time step: resolve old → kill-check → scan all → rank → open best.
        (Account hot-swap is handled in the 5s telemetry task, not here.)"""
        self.candle_idx += 1

        # Phase 1: Resolve matured positions (h=pred_len horizon elapsed)
        await self._resolve_positions()

        # Phase 2: Kill switch (equity-aware; may demand close-all)
        bal, equity, floating = await self._balance_equity_floating()
        killed, kreason, close_all = self.sentinel.check_kill(
            equity, len(self.open), symbols=runtime.active_symbols,
            floating_pnl=floating)
        if killed:
            if close_all and self.open:
                await self._close_all(f"kill:{kreason}")
            self.log(type="KILL", reason=kreason, bal=bal, equity=equity,
                     weekly_pnl=f"${self.sentinel.weekly_pnl:.2f}")
            try:
                db.log_risk_event("kill_switch", kreason,
                                  {"balance": bal, "equity": equity, "floating": floating})
            except Exception:
                pass
            return

        # Phase 3: Scan ALL symbols for signals
        signals = {}
        for sym in runtime.active_symbols:
            try:
                # Graceful skip: ignore active symbols the logged-in broker doesn't offer
                if hasattr(self.provider, "is_offered") and not self.provider.is_offered(sym):
                    self.log(type="SKIP", symbol=sym, reason="not offered by broker")
                    continue
                candles = await self.provider.get_candles(sym, settings.timeframe, settings.lookback + 5)
                sig = self.engine.get_signal(candles, sym)
                signals[sym] = sig
                try:
                    db.log_signal(sym, settings.timeframe, sig["direction"],
                                  sig["confidence"], sig["predicted_move"],
                                  sig["current_close"], sig["predicted_close"], sig["horizon"])
                except Exception:
                    pass
                try:
                    db.log_prediction(sym, settings.timeframe, sig["candle_time"],
                                      sig["predictions"], sig["predicted_close"],
                                      "UP" if sig["predicted_move"] > 0 else "DOWN",
                                      abs(sig["predicted_move"]),
                                      sig["lookback"], sig["pred_len"],
                                      sig["sample_count"], sig["inference_ms"])
                except Exception:
                    pass
            except Exception as e:
                self.log(type="ERROR", symbol=sym, msg=str(e))

        # Phase 4: Rank by |predicted_move| (descending), filter HOLDs + already-open
        tradeable = {sym: sig for sym, sig in signals.items()
                     if sig["direction"] != "HOLD" and sym not in self.open}
        ranked = sorted(tradeable.items(), key=lambda x: abs(x[1]["predicted_move"]), reverse=True)

        # Phase 5: Open positions (best first, up to max_open_positions)
        open_slots = runtime.max_open_positions - len(self.open)
        opened_syms = set()

        for sym, sig in ranked:
            if open_slots <= 0:
                break

            # Layer 2 gate — model-drift kill switch: if the model's recently RESOLVED
            # predictions are below coin-flip accuracy, block ALL trading this cycle.
            ok, reason = self.watcher.should_trade(sig)
            if not ok:
                self.log(type="DRIFT", msg=reason)
                try:
                    db.log_risk_event("drift", reason)
                except Exception:
                    pass
                break   # drift is global — stop opening for the rest of this cycle

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

            # Spread filter: skip if the spread eats the edge
            entry_proxy = sig["current_close"]
            spread = self.provider.get_spread(sym)
            spread_pct = spread / entry_proxy if entry_proxy else 0
            if spread_pct > settings.spread_max_of_move * abs(sig["predicted_move"]):
                self.log(type="SKIP", symbol=sym,
                         reason=f"spread {spread_pct:.3%} > {settings.spread_max_of_move * abs(sig['predicted_move']):.3%}")
                continue

            # Volatility gate: skip if the signal is lost in noise (low SNR)
            if sig["snr"] < settings.snr_min:
                self.log(type="SKIP", symbol=sym,
                         reason=f"low_snr {sig['snr']:.2f} < {settings.snr_min}")
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

            # Min-lot risk reality: lot is floored to 0.01, so the actual $-at-SL is
            # whatever min-lot dictates — NOT `risk`. Refuse to trade if that actual
            # risk exceeds risk_cap_pct of equity (the guard against the overnight
            # blowup where a single SL hit was ~$100 on a "$1 risk" trade).
            sl_dist_price = abs(entry - sig["sl_price"]) if sig["sl_price"] else 0.0
            actual_risk = lot * sl_dist_price * spec["contract_size"]
            cap = equity * runtime.risk_cap_pct
            if actual_risk > cap:
                self.log(type="SKIP", symbol=sym,
                         reason=f"risk ${actual_risk:.2f} > {runtime.risk_cap_pct:.0%} cap ${cap:.2f} "
                                f"(lot {lot} floored to min)")
                try:
                    db.log_risk_event("risk_cap_skip",
                                      f"{sym} actual ${actual_risk:.2f} > cap ${cap:.2f}",
                                      {"lot": lot, "sl_dist": sl_dist_price})
                except Exception:
                    pass
                continue

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
                "move": sig["predicted_move"],
                "actual_risk": actual_risk, "peak_profit": 0.0,
            }
            try:
                self.open[sym]["trade_id"] = db.log_trade_open(
                    sym, sig["direction"], entry, lot, sig["confidence"],
                    settings.pred_len, paper=False, ticket=ticket,
                    mt5_login=getattr(self.provider, "_login", None))
            except Exception:
                pass

            open_slots -= 1
            opened_syms.add(sym)
            self.log(type="OPEN", symbol=sym, dir=sig["direction"], lot=lot,
                     risk=f"${risk:.2f}", actual_risk=f"${actual_risk:.2f}",
                     conf=f"{sig['confidence']:.2f}", entry=entry)

            try:
                await send_telegram(
                    f"📡 OPEN {sym} {sig['direction']}\n"
                    f"Lot: {lot} | Risk @SL: ${actual_risk:.2f}\n"
                    f"Confidence: {sig['confidence']:.0%} | Entry: {entry:.2f}")
            except Exception:
                pass

        # Log summary
        holds = {sym: sig for sym, sig in signals.items() if sig["direction"] == "HOLD"}
        self.log(type="CYCLE", scanned=len(signals), tradeable=len(tradeable),
                 opened=len(opened_syms), open_total=len(self.open),
                 holds=len(holds), bal=bal, equity=equity,
                 weekly_pnl=f"${self.sentinel.weekly_pnl:.2f}")

    async def _resolve_positions(self):
        """Close positions whose h=pred_len horizon has elapsed."""
        for sym, pos in list(self.open.items()):
            if self.candle_idx - pos["entry_idx"] < settings.pred_len:
                continue
            try:
                candles = await self.provider.get_candles(sym, settings.timeframe, 5)
                cur = float(candles["close"].iloc[-1])
            except Exception:
                continue
            await self._close_position(sym, pos, exit_price=cur, reason="horizon")

    async def _close_position(self, sym, pos, exit_price=None, reason=""):
        """Close one real position, account P&L, log + Telegram. Shared by the
        horizon exit, the goal/ceiling bank, and kill close-all."""
        direction_sign = 1 if pos["direction"] == "BUY" else -1
        if exit_price is None:
            try:
                candles = await self.provider.get_candles(sym, settings.timeframe, 5)
                exit_price = float(candles["close"].iloc[-1])
            except Exception:
                exit_price = pos["entry_price"]
        price_diff = (exit_price - pos["entry_price"]) * direction_sign
        pnl = price_diff * pos["lot"] * pos["contract_size"]
        correct = price_diff > 0

        if pos.get("ticket"):
            try:
                await self.provider.close_position(pos["ticket"])
            except Exception as e:
                self.log(type="ERROR", msg=f"close failed {sym}: {e}")

        self.sentinel.on_trade_closed(pnl, correct)
        self.watcher.record_resolution(correct)

        bal = await self.get_balance()
        result_str = "WIN ✅" if correct else "LOSS ❌"
        self.log(type="CLOSE", symbol=sym, dir=pos["direction"], reason=reason,
                 entry=round(pos["entry_price"], 2), exit=round(exit_price, 2),
                 pnl=f"${pnl:+.2f}", result=result_str, bal=bal,
                 weekly_pnl=f"${self.sentinel.weekly_pnl:.2f}",
                 consec_losses=self.sentinel.consecutive_losses)

        try:
            db.log_trade_close(pos.get("trade_id"), exit_price, pnl,
                               "win" if correct else "loss")
        except Exception:
            pass

        try:
            await send_telegram(
                f"{'🟢' if correct else '🔴'} CLOSE {sym} {pos['direction']} ({reason})\n"
                f"P&L: ${pnl:+.2f} ({result_str})\n"
                f"Balance: ${bal:.2f}\n"
                f"Weekly P&L: ${self.sentinel.weekly_pnl:.2f} / ${runtime.weekly_goal:.2f}")
        except Exception:
            pass

        self.open.pop(sym, None)

    async def _close_all(self, reason):
        """Close every open position (used when the goal/ceiling is banked or a
        kill switch demands it)."""
        for sym in list(self.open.keys()):
            try:
                await self._close_position(sym, self.open[sym], reason=reason)
            except Exception as e:
                self.log(type="ERROR", msg=f"close_all failed {sym}: {e}")

    async def _reconcile_closed(self, open_tickets: set):
        """A position we track whose ticket is no longer at the broker was closed
        externally — SL hit between ticks, manual close, or a crash mid-close (the
        overnight bug: trades stuck at 'open' forever). Look up its realized outcome
        in the deal history and log the close so the trades tab stays accurate.
        Falls back to an estimate from the last price if the deal can't be found."""
        for sym, pos in list(self.open.items()):
            ticket = pos.get("ticket")
            if not ticket or ticket in open_tickets:
                continue
            exit_price, pnl, result = None, 0.0, "loss"
            deal = None
            if hasattr(self.provider, "get_closed_deal"):
                try:
                    deal = self.provider.get_closed_deal(ticket)
                except Exception:
                    deal = None
            if deal:
                pnl, exit_price = deal["pnl"], deal["price"]
                result = "win" if pnl > 0 else "loss"
            else:
                # deal not found (history window/permission) — estimate from last price
                try:
                    candles = await self.provider.get_candles(sym, settings.timeframe, 5)
                    exit_price = float(candles["close"].iloc[-1])
                except Exception:
                    exit_price = pos["entry_price"]
                direction_sign = 1 if pos["direction"] == "BUY" else -1
                pnl = (exit_price - pos["entry_price"]) * direction_sign \
                    * pos["lot"] * pos["contract_size"]
                result = "win" if pnl > 0 else "loss"
            correct = pnl > 0
            self.sentinel.on_trade_closed(pnl, correct)
            self.watcher.record_resolution(correct)
            self.log(type="CLOSE", symbol=sym, dir=pos["direction"], reason="external",
                     entry=round(pos["entry_price"], 2), exit=round(exit_price, 2),
                     pnl=f"${pnl:+.2f}", result=("WIN ✅" if correct else "LOSS ❌"),
                     weekly_pnl=f"${self.sentinel.weekly_pnl:.2f}")
            try:
                db.log_trade_close(pos.get("trade_id"), exit_price, pnl, result)
            except Exception:
                pass
            self.open.pop(sym, None)

    def _manage_exits(self, broker_positions):
        """Per-position SL management, called from telemetry every ~5s. Two tiers:
          1. profit-lock: once floating profit >= profit_lock_target, ratchet SL to
             lock max(profit_lock_min, peak_profit × profit_lock_fraction) of the gain.
          2. breakeven-lock: else, once favorable >= breakeven_lock_mult×|move|, slide
             SL to ~entry (downside only).
        Ratchets only (never widens). h=24 still the max hold. Uses the broker's
        live profit/price so it works for positions recovered after a restart."""
        if not self.open:
            return
        by_sym = {p["symbol"]: p for p in broker_positions}
        for sym, pos in list(self.open.items()):
            bp = by_sym.get(sym)
            ticket = pos.get("ticket")
            if not ticket or not bp:
                continue
            entry = pos["entry_price"]
            direction = pos["direction"]
            vol = pos.get("lot") or bp["volume"]
            cs = pos.get("contract_size") or 1.0
            cur = bp["price_current"]
            profit = bp.get("profit", 0.0)
            pos["peak_profit"] = max(pos.get("peak_profit", 0.0), profit)
            unit = vol * cs
            if unit <= 0:
                continue
            cur_sl = pos.get("sl_price")
            new_sl = None

            if profit >= runtime.profit_lock_target:
                locked = max(runtime.profit_lock_min,
                             pos["peak_profit"] * runtime.profit_lock_fraction)
                # SL price that realizes exactly `locked` of profit if hit
                new_sl = (entry + locked / unit) if direction == "BUY" else (entry - locked / unit)
            elif settings.breakeven_lock:
                move = pos.get("move")
                if move:
                    favorable_price = (cur - entry) if direction == "BUY" else (entry - cur)
                    threshold = settings.breakeven_lock_mult * abs(move) * entry
                    if favorable_price >= threshold:
                        new_sl = entry * (0.9999 if direction == "BUY" else 1.0001)

            if new_sl is None:
                continue
            new_sl = round(new_sl, 5)
            # safety: never place a stop BEYOND the current price (invalid / instant
            # trigger). For BUY the SL must be below cur; for SELL above it.
            if direction == "BUY" and new_sl >= cur:
                continue
            if direction == "SELL" and new_sl <= cur:
                continue
            # ratchet: only ever tighten (raise SL for BUY, lower for SELL)
            if cur_sl:
                tighter = (new_sl > cur_sl) if direction == "BUY" else (new_sl < cur_sl)
                if not tighter:
                    continue
            try:
                if self.provider.modify_sl(ticket, new_sl):
                    pos["sl_price"] = new_sl
                    self.log(type="TRAIL", symbol=sym,
                             msg=f"SL → {new_sl} (floating ${profit:.2f}, peak ${pos['peak_profit']:.2f})")
            except Exception as e:
                self.log(type="TRAIL_ERR", symbol=sym, msg=str(e))

    async def _maybe_bank_goal(self, equity, floating):
        """If the weekly goal is reached in equity (incl. floating) or realized+
        floating PnL, close ALL positions and latch the stop for the week. Called
        from telemetry so it reacts in ~5s, not the 300s cycle."""
        ceiling = runtime.baseline_equity + runtime.weekly_goal
        reached = (equity >= ceiling) or ((self.sentinel.weekly_pnl + floating) >= runtime.weekly_goal)
        if not reached or not self.open or self.sentinel.weekly_goal_locked:
            return
        self.log(type="GOAL", msg=f"banking weekly goal — equity ${equity:.2f} "
                 f"(ceiling ${ceiling:.2f}), pnl ${self.sentinel.weekly_pnl + floating:.2f}")
        try:
            db.log_risk_event("goal_banked",
                              f"equity ${equity:.2f} >= ceiling ${ceiling:.2f}")
        except Exception:
            pass
        await self._close_all("weekly_goal_banked")
        self.sentinel.weekly_goal_locked = True
        try:
            await send_telegram(
                f"🎯 Weekly goal banked (${runtime.weekly_goal:.2f}). "
                f"Closing all positions — resting for the week.")
        except Exception:
            pass

    async def _telemetry(self):
        """Near-realtime account heartbeat, independent of the (slow) trade cycle.
        Every ~5s: pull latest dashboard config (hot-reload), check for an MT5
        account switch, bank the weekly goal if reached, manage exits (profit/breakeven
        trail), then publish live balance / equity / floating PnL / positions / symbols."""
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
                # log closes for any tracked position the broker no longer has
                # (SL hit / manual close / crash mid-close) so trades don't stick at 'open'
                await self._reconcile_closed({p["ticket"] for p in positions})
                floating = round(sum(p.get("profit", 0) for p in positions), 2)
                # goal/ceiling bank (5s reaction) — else manage per-position exits
                await self._maybe_bank_goal(acct["equity"], floating)
                self._manage_exits(positions)
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
            # A new active account is a clean slate: drop the prior account's
            # in-memory positions (they don't exist on this login) and zero the
            # P&L/streak tracking so nothing carries over.
            self.open.clear()
            self.sentinel.reset_for_new_account()
            self.log(type="SWITCH", msg=f"switched to {self.provider.account_name} "
                     f"(login {getattr(self.provider, '_login', '?')}) — stats reset")
            try:
                await send_telegram(f"🔄 MT5 account switched to {self.provider.account_name} — fresh start")
            except Exception:
                pass
        except Exception as e:
            self.log(type="ERROR", msg=f"account switch failed: {e}")

    async def run(self, cycles=None, interval_sec=300):
        runtime.refresh()   # boot from the dashboard's last-saved config, not code defaults
        await self._reconcile_positions()   # never orphan an open trade across restarts
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
            sys.stdout = open(ROOT / "data" / "bot.log", "a", buffering=1,
                              encoding="utf-8", errors="replace")
        if sys.stderr is None:
            sys.stderr = open(ROOT / "data" / "bot.err", "a", buffering=1,
                              encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=int, default=None)
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--account", default=None)
    args = p.parse_args()
    trader = Trader(account=args.account)
    print(f"Holy Grail | LIVE | symbols={runtime.active_symbols} "
          f"tf={settings.timeframe} goal=${runtime.weekly_goal} "
          f"ceiling=${runtime.baseline_equity + runtime.weekly_goal}", flush=True)
    asyncio.run(trader.run(cycles=args.cycles, interval_sec=args.interval))
if __name__ == "__main__":
    main()
