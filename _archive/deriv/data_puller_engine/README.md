# _engines

Standalone, isolated tools — each a self-contained "engine" with its own code
and its own `data/` output folder. Run from the repo root with the project venv.

## Engines

| Engine | What it does | Run |
|--------|--------------|-----|
| **data_puller** | Interactive pull of Deriv synthetic-index tick history | `./venv/bin/python -m _engines.data_puller.pull` |

Adding a new engine: create `_engines/<name>/` (use `_` not `-` so it's importable)
with an `__init__.py`, its code, and a `data/` folder. Each engine is isolated —
it does not import from `research/` or the (future) bot packages.
