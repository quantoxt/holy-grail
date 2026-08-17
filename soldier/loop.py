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
import time
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

LOG = ROOT / "data" / "bot_log.jsonl"   # was paper_log.jsonl — this is the LIVE audit log
CYCLE_SEC = 300   # --interval default; used to age reconciled positions


class Trader:
    def __init__(self, account=None):
        self.provider = get_provider(account=account)
        self.engine = SignalEngine()
        self.watcher = Watcher()
        self.sentinel = sentinel_inst
        self.open: dict = {}
        self.candle_idx = 0
        self.closed_until: dict = {}   # symbol → epoch until which its market is closed (10018 backoff)
        self.pending_deals: list = []  # closes whose deal wasn't in history yet → retried ~60s
        self.kill_latched: bool = False  # last cycle's kill-switch state (orphan closer)
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
        self.kill_latched = killed   # telemetry uses this to force-close orphans
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
            # Shadow measurement: a latched week (goal banked / blackout / stopped)
            # is exactly when the CPU is idle — keep scoring predictions so the
            # per-symbol accuracy data accumulates even without trading.
            if runtime.bot_running and not runtime.trading_paused:
                await self._scan_signals()
            return

        # Phase 3: Scan ALL symbols for signals
        signals = await self._scan_signals()

        # Phase 4: Rank by |predicted_move| (descending), filter HOLDs + already-open
        # + low-confidence (observed 2026-08-10: sub-50% confidence trades closed at a loss)
        tradeable = {sym: sig for sym, sig in signals.items()
                     if sig["direction"] != "HOLD" and sym not in self.open
                     and sig["confidence"] >= runtime.min_confidence}
        ranked = sorted(tradeable.items(), key=lambda x: abs(x[1]["predicted_move"]), reverse=True)

        # Phase 5: Open positions (best first, up to max_open_positions)
        # Slot count uses the BROKER's real position count too — the bot's memory
        # can undercount (an orphaned open, a failed tracking) and over-opening
        # real money is the one unforgivable direction to be wrong in.
        broker_open = 0
        try:
            broker_open = len(await self.provider.get_open_positions())
        except Exception:
            broker_open = len(self.open)
        open_slots = runtime.max_open_positions - max(len(self.open), broker_open)
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
            # (also skip closed sessions — stale tick OR a recent 10018 rejection;
            # brokers keep quoting after the book closes, so the retcode is truth)
            if self.closed_until.get(sym, 0) > time.time():
                self.log(type="SKIP", symbol=sym, reason="market closed (10018 backoff)")
                continue
            if hasattr(self.provider, "is_open") and not self.provider.is_open(sym):
                self.log(type="SKIP", symbol=sym, reason="market closed (stale tick)")
                continue
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
                if result.get("retcode") == 10018:   # market closed — back off 1h
                    self.closed_until[sym] = time.time() + 3600
                    self.log(type="SKIP", symbol=sym, reason="market closed (retcode 10018), backing off 1h")
                    continue
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
                # Exit target: volatility-sized when tp_vol_mult>0 (predicted magnitude
                # carries no info — corr(pred,actual) ≈ 0), else a fraction of the
                # predicted move (1.0 = exactly Kronos's predicted close).
                "target_price": (
                    entry + (runtime.tp_vol_mult * sig["vol"] * entry)
                    if (runtime.tp_vol_mult > 0 and sig.get("vol"))
                    else entry + runtime.tp_fraction * (sig["predicted_close"] - entry)),
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

    async def _scan_signals(self) -> dict:
        """Phase 3: run Kronos over every active symbol, log signals/predictions/
        evaluations. Returns {symbol: signal}. Used by the trade cycle AND by the
        latched-week shadow measurement (scoring predictions needs no trading)."""
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
                # measurement loop: score EVERY prediction (traded or not) later
                try:
                    db.log_evaluation(sym, settings.timeframe, sig["direction"],
                                      sig["predicted_move"], sig["predicted_close"],
                                      sig["current_close"], sig["confidence"],
                                      sig["snr"], sig["sample_count"],
                                      horizon_min=settings.pred_len * 5)
                except Exception:
                    pass
            except Exception as e:
                self.log(type="ERROR", symbol=sym, msg=str(e))
        return signals

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
            # broker-truth P&L from the closing deal (incl. swap/commission);
            # falls back to the estimate if the deal can't be found yet — the
            # broker's history index lags a close by minutes, so queue a retry
            if hasattr(self.provider, "get_closed_deal"):
                try:
                    deal = self.provider.get_closed_deal(pos["ticket"])
                except Exception:
                    deal = None
                if deal:
                    pnl, exit_price = deal["pnl"], deal["price"]
                    correct = pnl > 0
                elif pos.get("trade_id"):
                    self.pending_deals.append(
                        {"trade_id": pos["trade_id"], "ticket": pos["ticket"]})

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
            elif pos.get("trade_id"):
                # deal not in history yet — correct the row from telemetry later
                self.pending_deals.append(
                    {"trade_id": pos["trade_id"], "ticket": ticket})
            if not deal:
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

    def _reconcile_pending_deals(self):
        """Retry deal lookups for closes the broker hadn't indexed yet. The MT5
        history API lags a close by minutes — the first lookup right after close
        often returns None and the trades row gets a price-diff estimate. Once
        the real deal appears, correct the row with broker truth (pnl incl.
        swap/commission, actual fill price)."""
        if not self.pending_deals:
            return
        still_pending = []
        for p in self.pending_deals:
            try:
                deal = self.provider.get_closed_deal(p["ticket"])
            except Exception:
                deal = None
            if not deal:
                still_pending.append(p)
                continue
            result = "win" if deal["pnl"] > 0 else "loss"
            try:
                db.update_trade_result(p["trade_id"], deal["price"], deal["pnl"], result)
            except Exception:
                pass
            self.log(type="DEAL_FIX", ticket=p["ticket"], pnl=f"${deal['pnl']:+.2f}",
                     exit=deal["price"], msg="trades row corrected with broker deal")
        self.pending_deals = still_pending

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

            # Thresholds are R-based when the trade's actual $-at-SL is known:
            # min-lot trades float only ±$1-2 on BTC, so the old FIXED $5 trigger
            # could never fire — winners round-tripped to breakeven before horizon.
            risk_ref = pos.get("actual_risk") or 0.0
            trail_target = (runtime.profit_lock_r * risk_ref) if risk_ref > 0 \
                else runtime.profit_lock_target
            be_target = (runtime.breakeven_lock_r * risk_ref) if risk_ref > 0 else None

            if profit >= trail_target:
                locked = max((min(runtime.profit_lock_min, 0.5 * risk_ref) if risk_ref > 0
                              else runtime.profit_lock_min),
                             pos["peak_profit"] * runtime.profit_lock_fraction)
                # SL price that realizes exactly `locked` of profit if hit
                new_sl = (entry + locked / unit) if direction == "BUY" else (entry - locked / unit)
            elif be_target is not None:
                if profit >= be_target:
                    new_sl = entry * (0.9999 if direction == "BUY" else 1.0001)
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

    async def _maybe_take_targets(self, broker_positions):
        """Predicted-level take-profit: when live price reaches Kronos's predicted
        close, the forecast has played out — take the profit rather than holding to
        the h=24 horizon. Fixes path dependency (a winner can reverse to SL before
        horizon) and frees the slot for the next signal. Recovered positions have
        no stored target and are simply skipped."""
        if not runtime.tp_at_predicted or not self.open:
            return
        by_sym = {p["symbol"]: p for p in broker_positions}
        for sym, pos in list(self.open.items()):
            target = pos.get("target_price")
            bp = by_sym.get(sym)
            cur = bp.get("price_current") if bp else None
            if not target or not cur:
                continue
            hit = cur >= target if pos["direction"] == "BUY" else cur <= target
            if hit:
                await self._close_position(sym, pos, exit_price=cur, reason="target")

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
        eval_every = 12         # resolve matured predictions every ~60s
        last_prune_day = None   # prune kronos_predictions once per UTC day
        tick = 0
        while True:
            try:
                await asyncio.sleep(5)
                tick += 1
                runtime.refresh()                                   # hot-reload dashboard edits
                await self._maybe_switch_account()                  # dashboard-driven swap
                if tick % eval_every == 0:
                    await self._resolve_evaluations()               # score matured predictions
                    self._reconcile_pending_deals()                # correct lagged deal P&L
                today = datetime.now(timezone.utc).date()
                if last_prune_day != today:
                    last_prune_day = today
                    try:
                        db.prune_predictions(days=7)
                    except Exception:
                        pass
                acct = await self.provider.account_summary()
                positions = await self.provider.get_open_positions()
                # log closes for any tracked position the broker no longer has
                # (SL hit / manual close / crash mid-close) so trades don't stick at 'open'
                await self._reconcile_closed({p["ticket"] for p in positions})
                # SAFETY NET: a broker position the bot is NOT tracking is an orphan
                # (opened by a post-order crash, a restart that lost state, anything).
                # While kill-latched the book must be FLAT — force-close orphans.
                tracked = {p.get("ticket") for p in self.open.values()}
                orphans_were_closed = False
                if getattr(self, "kill_latched", False):
                    for bp in positions:
                        if bp["ticket"] in tracked:
                            continue
                        try:
                            await self.provider.close_position(bp["ticket"])
                            self.log(type="ORPHAN_CLOSE", symbol=bp["symbol"],
                                     ticket=bp["ticket"], pnl=f"${bp.get('profit', 0):+.2f}",
                                     msg="untracked position force-closed during kill-latch")
                            orphans_were_closed = True
                        except Exception as e:
                            self.log(type="ORPHAN_CLOSE_ERR", symbol=bp["symbol"], msg=str(e))
                    if orphans_were_closed:
                        positions = await self.provider.get_open_positions()
                floating = round(sum(p.get("profit", 0) for p in positions), 2)
                # goal/ceiling bank (5s reaction), predicted-level TP, then trails
                await self._maybe_bank_goal(acct["equity"], floating)
                await self._maybe_take_targets(positions)
                positions = await self.provider.get_open_positions()  # refresh post-close
                self._manage_exits(positions)
                syms = self.provider.discover_symbols(force=(tick % sym_refresh_every == 0))
                # Balance-based weekly P&L for the dashboard card. Deal-history sums
                # (realized_since) MISS closes made in the last minutes-to-hours
                # (broker history index lag) — balance arithmetic cannot. Weekly =
                # balance − week_start_balance − net deposits/withdrawals this week.
                weekly_pnl = None
                if hasattr(self.provider, "cashflow_since"):
                    try:
                        now_d = datetime.now(timezone.utc)
                        wk = now_d.date()
                        wk = wk.fromordinal(wk.toordinal() - wk.weekday())   # Monday 00:00
                        wk_ts = datetime(wk.year, wk.month, wk.day, tzinfo=timezone.utc).timestamp()
                        wk_iso = wk.isoformat()
                        if runtime.week_start_monday != wk_iso:
                            # New week (or first boot with this feature): snapshot the
                            # week's opening balance. On a clean Monday rollover there
                            # are no deals yet, so this is just the current balance; on
                            # a mid-week first boot we back out this week's cashflow and
                            # realized deals so the snapshot equals "balance at Monday".
                            cash = self.provider.cashflow_since(wk_ts) or 0.0
                            real = self.provider.realized_since(wk_ts) or 0.0
                            runtime.week_start_balance = round(acct["balance"] - cash - real, 2)
                            runtime.week_start_monday = wk_iso
                            runtime.persist()
                            self.log(type="WEEK_SNAPSHOT", monday=wk_iso,
                                     week_start_balance=runtime.week_start_balance,
                                     msg="balance snapshot for balance-based weekly P&L")
                        cash = self.provider.cashflow_since(wk_ts) or 0.0
                        weekly_pnl = round(acct["balance"] - runtime.week_start_balance - cash, 2)
                        # keep Sentinel on broker truth so Telegram + kill checks
                        # agree with the dashboard card
                        self.sentinel.weekly_pnl = weekly_pnl
                    except Exception:
                        weekly_pnl = None
                # all-time realized (Net P&L card) — refresh less often, it's stable
                realized_pnl = None
                if hasattr(self.provider, "realized_since") and tick % sym_refresh_every == 1:
                    try:
                        realized_pnl = self.provider.realized_since(0)
                    except Exception:
                        realized_pnl = None
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
                    news_blackout=blackout, news_reason=reason, weekly_pnl=weekly_pnl,
                    realized_pnl=realized_pnl)
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
            # Weekly P&L snapshot is per-ACCOUNT, not per-bot: a balance snapshotted
            # on the old login makes the card compute balance(new) − snapshot(old) —
            # garbage. Clear it so telemetry re-snapshots for this login in ~5s.
            runtime.week_start_balance = None
            runtime.week_start_monday = ""
            runtime.persist()
            self.log(type="SWITCH", msg=f"switched to {self.provider.account_name} "
                     f"(login {getattr(self.provider, '_login', '?')}) — stats reset")
            try:
                await send_telegram(f"🔄 MT5 account switched to {self.provider.account_name} — fresh start")
            except Exception:
                pass
        except Exception as e:
            self.log(type="ERROR", msg=f"account switch failed: {e}")

    def _reload_pnl_from_broker(self):
        """Seed Sentinel's in-memory weekly/daily P&L from the broker's deal history
        so a restart doesn't zero them (a restarted bot used to think the week was
        $0 and mislabel the equity-ceiling kill as 'weekly_goal_hit ($0.00 >= ...)').
        Best-effort: on any failure the old zero-start behavior applies."""
        if not hasattr(self.provider, "realized_since"):
            return
        try:
            now_d = datetime.now(timezone.utc)
            d = now_d.date()
            monday = d.fromordinal(d.toordinal() - d.weekday())
            wk = self.provider.realized_since(
                datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc).timestamp())
            if wk is not None:
                self.sentinel.weekly_pnl = wk
            dy = self.provider.realized_since(
                datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
            if dy is not None:
                self.sentinel.daily_pnl = dy
            self.sentinel.last_day = d
            self.sentinel.last_week_start = monday
            self.log(type="RELOAD_PNL", weekly=f"${self.sentinel.weekly_pnl:.2f}",
                     daily=f"${self.sentinel.daily_pnl:.2f}", msg="seeded from broker deal history")
        except Exception as e:
            self.log(type="RELOAD_PNL_ERR", msg=str(e))

    async def _resolve_evaluations(self):
        """Score matured predictions against the actual close at due_time — ALL
        predictions, traded or not. This is the measurement loop: per-symbol
        accuracy, N-sample comparison, and confidence calibration all come from
        the prediction_evaluations table. Also feeds the Watcher's drift check."""
        import pandas as pd
        try:
            rows = db.due_evaluations(15)
        except Exception:
            return
        for r in rows:
            try:
                candles = await self.provider.get_candles(r["symbol"], settings.timeframe, 48)
                ts = pd.to_datetime(candles["timestamps"])
                due = pd.Timestamp(r["due_time"])
                due = due.tz_convert("UTC").tz_localize(None) if due.tzinfo else due
                idx = int(ts.searchsorted(due))
                if idx >= len(candles):
                    continue   # candle not available yet; retry next pass
                actual = float(candles["close"].iloc[idx])
                base = float(r["current_close"] or 0) or actual
                actual_move = (actual - base) / base
                if actual_move == 0:
                    outcome = "flat"
                elif (actual_move > 0) == ((r["predicted_move"] or 0) > 0):
                    outcome = "hit"
                else:
                    outcome = "miss"
                db.resolve_evaluation(r["id"], outcome, actual, actual_move)
                if r["direction"] != "HOLD":
                    self.watcher.record_resolution(outcome == "hit")
            except Exception as e:
                self.log(type="EVAL_ERR", symbol=r.get("symbol"), msg=str(e))

    def _seed_watcher(self):
        """Bootstrap the drift window from resolved evaluations so a restart no
        longer wipes Layer 2 back to warmup (it was effectively dead in prod)."""
        try:
            rows = db.recent_resolved_evaluations(limit=20)
            for r in reversed(rows):   # oldest → newest
                self.watcher.record_resolution(r["outcome"] == "hit")
            if rows:
                self.log(type="WATCHER", msg=f"seeded rolling accuracy "
                         f"{self.watcher.rolling_accuracy:.0%} from {len(rows)} evaluations")
        except Exception:
            pass

    async def run(self, cycles=None, interval_sec=300):
        runtime.refresh()   # boot from the dashboard's last-saved config, not code defaults
        await self._reconcile_positions()   # never orphan an open trade across restarts
        self._reload_pnl_from_broker()      # restart must not zero weekly/daily P&L
        self._seed_watcher()                # drift window survives restarts too
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
