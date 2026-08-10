# Holy Grail — Operator's Manual

This folder is your self-service reference for understanding, running, and fixing the bot.
Read top-to-bottom the first time; jump to a specific doc after that. Everything here is
written in plain language — no assumed context.

## The 30-second mental model

A pre-trained AI model (**Kronos**) predicts where price will be in 2 hours. When it calls
a direction with enough conviction, the **Soldier** layer opens a trade. The **Sentinel**
(risk manager) decides how big, when to stop, and banks the weekly profit. The **Watcher**
kills trading if the AI's accuracy drifts to coin-flip. Everything runs on a Windows VPS
connected to one MT5 broker; a web dashboard (Vercel) shows live state and lets you tweak
settings live. The database (Supabase cloud) is the glue between the bot and the dashboard.

```
Kronos predicts  →  Soldier trades  →  Sentinel sizes/protects  →  Watcher guards accuracy
        ↑                                                                  ↓
        └──────────── MT5 broker (orders) + Supabase (state) + Dashboard ──┘
```

## Doc index

| Doc | Read this when you want to… |
|---|---|
| **[architecture.md](architecture.md)** | Understand what each piece is and how data flows. |
| **[risk-framework.md](risk-framework.md)** | Understand goals, caps, stops, lot sizing, kill switches. |
| **[configuration.md](configuration.md)** | Know what every setting does and how to change it. |
| **[running-the-bot.md](running-the-bot.md)** | Start/stop/restart/deploy, and what a cycle does. |
| **[dashboard-guide.md](dashboard-guide.md)** | Use each dashboard view and the controls. |
| **[trade-lifecycle.md](trade-lifecycle.md)** | See exactly how a trade opens and all the ways it exits. |
| **[accounts-and-brokers.md](accounts-and-brokers.md)** | Switch accounts, broker min-lot/symbol quirks. |
| **[kronos-predictions.md](kronos-predictions.md)** | Understand the AI and the "long-shot SL" problem. |
| **[vps-troubleshooting.md](vps-troubleshooting.md)** | Something's wrong — debug by symptom. |

## Other reference files (one level up, in `_internal/`)
- `../observations.md` — your raw notes from the 2026-08-10 overnight run (the incident that drove most of the current safety logic).
- `../fine-tune.md` — the original risk-framework spec (background; the live code supersedes parts of it).
- `../build/frontend-plan.md` — the dashboard design notes.

## The five things you'll do most
1. **Check it's alive + trading:** see `vps-troubleshooting.md` §1–3 (the cheat sheet at §13).
2. **Change risk / goal / symbols live:** `configuration.md` + the dashboard Config view — no restart needed.
3. **Switch MT5 account:** `accounts-and-brokers.md` (activate in dashboard; bot hot-swaps).
4. **Restart after a code deploy:** `running-the-bot.md` (kill → confirm empty → run).
5. **Diagnose "no trades":** it's almost always (a) broker min-lot vs cap, or (b) symbols not resolving — see `vps-troubleshooting.md` §6.

## Golden rules (learned the hard way)
- **The cap isn't the enemy; min-lot is.** A 0.1-min-lot broker on a small account blocks everything for a reason. Switch brokers or fund bigger — don't just raise the cap.
- **Kill → confirm empty → run.** A dashboard "restart" can't relaunch a dead process; and `schtasks /run` is a silent no-op if one's already running.
- **Kronos's edge is directional + BTCUSD-only.** Magnitude forecasts are un-calibrated; don't trust predicted move *sizes*, only the *sign*.
- **Never commit/push without being asked.** The service_role key stays off the VPS and out of Vercel.
