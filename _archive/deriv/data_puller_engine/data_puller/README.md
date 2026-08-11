# data_puller engine

Interactive puller for Deriv synthetic-index tick history. Self-contained —
reads credentials from the repo-root `.env` and writes data into this folder's
own `data/` directory.

## Usage

From the repo root:

```bash
# interactive — pick symbol from a menu, enter days, confirm
./venv/bin/python -m _engines.data_puller.pull

# non-interactive
./venv/bin/python -m _engines.data_puller.pull --symbol R_75 --days 90

# extend existing data further back (resumable)
./venv/bin/python -m _engines.data_puller.pull --symbol R_75 --days 180 --resume

# just see the plan, don't pull
./venv/bin/python -m _engines.data_puller.pull --symbol R_75 --days 90 --dry-run
```

## Output

This engine is the **trusted writer of ticks** for the project, so it writes to
the **shared** data root (not an engine-local folder):

```
<repo>/data/ticks/            ← shared project data root
  <SYMBOL>/
    2026-05-04.csv.gz         # columns: epoch,price  (gzipped, one file per UTC day)
    ...
    _checkpoint.json          # resume cursor + totals
```

Other engines/tools (OHLCV builder, backtester, the bot) read from `data/ticks/`.
Engines that need *private* data can still keep a local `data/` folder.

## Notes

- Uses the **new PAT/Options API** (PAT → OTP → authenticated WS). No `python-deriv-api`.
- The API caps `ticks_history` at **1000 ticks/request**; standard synthetics tick ~2/sec.
- Pulls are **append-safe + deduped** and **resumable** — kill and re-run anytime;
  `--resume` extends backward from where you stopped.
- Pulling is I/O-bound and light on CPU, but avoid running it alongside the
  fine-tune trainer (RAM contention froze an 8 GB laptop once).
