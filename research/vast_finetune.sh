#!/usr/bin/env bash
# BTCUSD fine-tune on a rented VAST GPU box (RTX 5060 Ti).
#
# Ship the repo + candles first (from YOUR machine):
#   tar czf /tmp/hg.tgz --exclude=.env --exclude=venv-torch --exclude=node_modules \
#       --exclude=.git --exclude=_archive --exclude=data/models .
#   scp -i ~/.ssh/id_ed25519_vast -P <PORT> /tmp/hg.tgz root@<HOST>:/root/
#   ssh -i ~/.ssh/id_ed25519_vast -p <PORT> root@<HOST>
# On the box:
#   tar xzf hg.tgz && cd holy-grail* && bash research/vast_setup.sh   # once
#   nohup bash research/vast_finetune.sh > data/finetune_btc.log 2>&1 &
#
# Stages: 1) split 50/50  2) fine-tune (tokenizer + predictor)  3) walk-forward
# validation on the held-out half ONLY  4) magnitude-calibration report.
# Everything logs; training writes to model/Kronos/finetune_csv/finetuned/btcusd_m5_5050.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PY:-python3}"

echo "== env =="
$PY - <<'EOF'
import torch
assert torch.cuda.is_available(), "no CUDA — run research/vast_setup.sh first"
print(f"torch {torch.__version__} | {torch.cuda.get_device_name(0)}")
EOF

echo "== stage 1: 50/50 split =="
$PY - <<'EOF'
import pandas as pd
df = pd.read_csv("data/ohlcv/BTCUSD/5m.csv")
half = len(df) // 2
tr = df.iloc[:half]
tr.to_csv("data/ohlcv/BTCUSD/5m_train.csv", index=False)
print(f"total {len(df)} candles; train half {len(tr)} "
      f"({tr['timestamps'].iloc[0]} → {tr['timestamps'].iloc[-1]}); "
      f"held-out test {len(df)-half} ({df['timestamps'].iloc[half]} → {df['timestamps'].iloc[-1]})")
open("data/ohlcv/BTCUSD/test_size.txt", "w").write(str(len(df) - half))
EOF
TEST_SIZE="$(cat data/ohlcv/BTCUSD/test_size.txt)"

echo "== stage 2: fine-tune (tokenizer + basemodel) =="
cd model/Kronos/finetune_csv
$PY train_sequential.py --config configs/btcusd_m5_5050.yaml
cd "$ROOT"

echo "== stage 3: walk-forward validation on held-out half (fine-tuned model) =="
$PY -m research.validate \
  --symbol BTCUSD --tf 5m \
  --model-dir model/Kronos/finetune_csv/finetuned/btcusd_m5_5050 \
  --test-size "$TEST_SIZE" \
  --stride 24 --pred-len 24 --sample-count 5

echo "== stage 4: magnitude calibration report (fine-tuned vs realized) =="
$PY - <<'EOF'
import json, glob, math
# newest fine-tuned checkpoint for this run
ck = sorted(glob.glob("data/validate_BTCUSD_5m_n5.jsonl"))
rows = [json.loads(l) for l in open(ck[-1])]
pairs = [(abs(r["predicted_move"]), abs(r["actual_move"])) for r in rows
         if r.get("actual_move") is not None]
n = len(pairs)
if n:
    p = [a for a, b in pairs]; a = [b for a, b in pairs]
    mp = sum(p) / n; ma = sum(a) / n
    cov = sum((x - mp) * (y - ma) for x, y in pairs) / n
    sp = math.sqrt(sum((x - mp) ** 2 for x in p) / n)
    sa = math.sqrt(sum((y - ma) ** 2 for y in a) / n)
    ratios = sorted(y / x for x, y in pairs if x > 0)
    med = ratios[len(ratios) // 2]
    print(f"n={n}  corr(pred,actual size)={cov/(sp*sa):+.3f}  "
          f"median actual/pred={med:.3f}  (pre-finetune: corr≈0, median≈0.2)")
    print("PASS direction gate if h=24 accuracy >= 55% (see report above)")
EOF

echo "== all done — log: data/finetune_btc.log; model: model/Kronos/finetune_csv/finetuned/btcusd_m5_5050 =="
echo "== copy home: scp -i ~/.ssh/id_ed25519_vast -P <PORT> 'root@<HOST>:/root/holy-grail*/data/validate_BTCUSD*.jsonl' data/ =="
