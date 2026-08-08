"""Holy Grail trading loop — Sentinel v2 integration.

Goal-driven risk management (weekly $14 goal on $50 account). Time-based exit
at h=24 + hard SL safety net (no 3:1 TP). Real orders on MT5 demo (--live).
All risk params are dashboard-adjustable via RuntimeConfig.

Run (Windows, MT5 live):
  python -m soldier.loop --live --account demo
Run (paper, for testing):
  python -m soldier.loop --cycles 1 --interval 0
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
from sentinel.risk import sentinel as sentinel_instance  # noqa: E402

LOG = ROOT / "data" / "paper_log.jsonl"


class Trader:
    def __init__(self, account=None, live=False):
        self.provider = get_provider(settings.market_mode, account=account)
        self.engine = SignalEngine()
        self.watcher = Watcher()
        self.sentinel = sentinel_instance
        self.open: dict = {}
        self.candle_idx = 0
        self.live = live
        LOG.parent.mkdir(parents=True, exist_ok=True)

    def log(self, **kw):
        kw["ts"] = datetime.now(timezone.utc).isoformat()
        with open(LOG, "a") as f:
            f.write(json.dumps(kw) + "\n")
        print("[" + kw.get("type", "") + "] " +
              " ".join(f"{k}={v}" for k, v in kw.items() if k not in ("ts", "type")))

    async def cycle(self, symbol: str):
        self.candle_idx += 1
        candles = await self.provider.get_candles(symbol, settings.timeframe, settings.lookback + 5)
        cur = float(candles["close"].iloc[-1])

        # candle date for weekly/daily resets
        candle_date = datetime.fromisoformat(str(candles["timestamps"].iloc[-1])).date()
        self.sentinel.check_time_resets(candle_date)

        # 1) resolve matured positions (h=pred_len horizon elapsed)
        for sym, pos in list(self.open.items()):
            if self.candle_idx - pos["entry_idx"] >= settings.pred_len:
                # compute P&L from prices (works for both paper + live)
                direction_sign = 1 if pos["direction"] == "BUY" else -1
                price_diff = (cur - pos["entry_price"]) * direction_sign
                pnl = price_diff * pos["lot"] * pos["contract_size"]
                correct = price_diff > 0

                # close the real position if live
                if self.live and pos.get("ticket"):
                    try:
                        await self.provider.close_position(pos["ticket"])
                    except Exception as e:
                        self.log(type="ERROR", msg=f"close failed: {e}")

                self.sentinel.on_trade_closed(pnl, correct)
                self.watcher.record_resolution(correct)
                self.log(type="CLOSE", symbol=sym, dir=pos["direction"],
                         entry=round(pos["entry_price"], 2), exit=round(cur, 2),
                         pnl=f"${pnl:+.2f}", correct=correct,
                         weekly_pnl=f"${self.sentinel.weekly_pnl:.2f}",
                         consec_losses=self.sentinel.consecutive_losses)
                try:
                    db.log_trade_close(pos.get("trade_id"), cur, pnl,
                                       "win" if correct else "loss")
                except Exception:
                    pass
                del self.open[sym]

        # 2) new signal
        sig = self.engine.get_signal(candles)
        try:
            db.log_signal(symbol, settings.timeframe, sig["direction"],
                          sig["confidence"], sig["predicted_move"],
                          sig["current_close"], sig["predicted_close"], sig["horizon"])
        except Exception:
            pass

        # 3) Sentinel v2: kill switches
        bal = 50.0  # baseline (anti-compounding)
        if self.live:
            try:
                bal = (await self.provider.get_balance()).get("balance", 50.0)
            except Exception:
                pass
        killed, kreason = self.sentinel.check_kill(bal, len(self.open),
                                                      symbols=runtime.active_symbols)
        trade, wreason = self.watcher.should_trade(sig)

        action = "HOLD"
        if killed:
            action = f"KILLED({kreason})"
            try:
                db.log_risk_event("kill_switch", kreason, {"balance": bal})
            except Exception:
                pass
        elif trade and symbol not in self.open and sig["sl_price"]:
            # 4) compute risk + lot
            risk = self.sentinel.risk_amount(sig["confidence"], candle_date)
            spec = await self.provider.get_symbol_info(symbol)
            lot = self.sentinel.lot_size(
                risk, cur, sig["sl_price"],
                spec["contract_size"], spec["volume_min"], spec["volume_step"])

            if lot >= spec["volume_min"] and risk > 0:
                # 5) execute
                ticket = None
                if self.live:
                    try:
                        result = await self.provider.open_position(
                            symbol, sig["direction"], lot, sl=sig["sl_price"])
                        ticket = result.get("id")
                        if not result.get("ok", True) and not ticket:
                            self.log(type="ERROR", msg=f"order rejected: {result}")
                            lot = 0
                    except Exception as e:
                        self.log(type="ERROR", msg=f"open failed: {e}")
                        lot = 0

                if lot > 0:
                    self.open[symbol] = {
                        "direction": sig["direction"], "entry_price": cur,
                        "entry_idx": self.candle_idx, "lot": lot,
                        "contract_size": spec["contract_size"],
                        "ticket": ticket, "trade_id": None, "sl_price": sig["sl_price"],
                    }
                    try:
                        self.open[symbol]["trade_id"] = db.log_trade_open(
                            symbol, sig["direction"], cur, risk, sig["confidence"],
                            settings.pred_len, paper=not self.live)
                    except Exception:
                        pass
                    action = (f"{'LIVE' if self.live else 'PAPER'} OPEN {sig['direction']} "
                              f"lot={lot} risk=${risk:.2f} sl={sig['sl_price']:.2f}")
                    try:
                        await send_telegram(
                            f"HOLY GRAIL | OPEN {symbol} {sig['direction']} "
                            f"lot={lot} risk=${risk:.2f} conf={sig['confidence']:.0%}")
                    except Exception:
                        pass
            else:
                action = f"SKIP (lot={lot} < min={spec['volume_min']})"

        self.log(type="SIGNAL", symbol=symbol, dir=sig["direction"],
                 move=f"{sig['predicted_move']:.3%}", conf=f"{sig['confidence']:.2f}",
                 action=action, bal=bal, open_count=len(self.open),
                 weekly_pnl=f"${self.sentinel.weekly_pnl:.2f}")

    async def run(self, cycles=None, interval_sec=300):
        c = 0
        try:
            while cycles is None or c < cycles:
                if not runtime.bot_running:
                    self.log(type="STATUS", msg="bot_stopped via dashboard")
                    await asyncio.sleep(10)
                    continue
                for sym in runtime.active_symbols:
                    await self.cycle(sym)
                c += 1
                if (cycles is None or c < cycles) and interval_sec > 0:
                    await asyncio.sleep(interval_sec)
        finally:
            try:
                await self.provider.ex.close()
            except Exception:
                pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=int, default=None)
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--account", default=None)
    p.add_argument("--live", action="store_true")
    args = p.parse_args()
    trader = Trader(account=args.account, live=args.live)
    print(f"Holy Grail | mode={settings.market_mode} symbols={runtime.active_symbols} "
          f"tf={settings.timeframe} goal=${runtime.weekly_goal} live={args.live}")
    asyncio.run(trader.run(cycles=args.cycles, interval_sec=args.interval))


if __name__ == "__main__":
    main()
