#!/usr/bin/env bash
# Per-instrument validation on a rented VAST GPU box (RTX 5060 Ti, CUDA 13.x).
#
# On YOUR machine, ship the repo (no .env) + candles to the box first:
#   tar czf /tmp/hg.tgz --exclude=.env --exclude=venv-torch --exclude=node_modules \
#       --exclude=.git --exclude=_archive .
#   scp -i ~/.ssh/id_ed25519_vast -P <PORT> /tmp/hg.tgz root@85.218.235.6:/root/
#   ssh -i ~/.ssh/id_ed25519_vast -p <PORT> root@85.218.235.6
# Then on the box:
#   tar xzf hg.tgz && cd holy-grail* && bash research/vast_run.sh
#
# Runs walk-forward validation (stride 24, full ~13-month history, N=5 averaged)
# for XAUUSD, XAGUSD, GBPUSD. RESUMABLE — validate.py checkpoints per prediction,
# so re-running this script after any interruption continues where it left off.
set -euo pipefail
cd "$(dirname "$0")/.."

SYMBOLS="${SYMBOLS:-XAUUSD XAGUSD GBPUSD}"
STRIDE="${STRIDE:-24}"
SAMPLES="${SAMPLES:-5}"
PY="${PY:-python3}"

echo "== env =="
$PY - <<'EOF'
import torch
assert torch.cuda.is_available(), "no CUDA — wrong torch build?"
print(f"torch {torch.__version__} | cuda {torch.version.cuda} | {torch.cuda.get_device_name(0)}")
EOF

echo "== validate: stride=$STRIDE N=$SAMPLES symbols: $SYMBOLS =="
for sym in $SYMBOLS; do
  echo "--- $sym ---"
  $PY -m research.validate \
    --symbol "$sym" --tf 5m \
    --pretrained \
    --test-size 200000 \
    --stride "$STRIDE" \
    --pred-len 24 \
    --sample-count "$SAMPLES"
done

echo
echo "== all done — reports above; checkpoints in data/validate_*.jsonl =="
echo "== copy results home:  scp -i ~/.ssh/id_ed25519_vast -P <PORT> "
echo "      'root@85.218.235.6:/root/holy-grail*/data/validate_*.jsonl' data/ =="
