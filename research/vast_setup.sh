#!/usr/bin/env bash
# One-time box setup: PyTorch with CUDA 12.8 wheels (Blackwell sm_120 needs
# cu128+) + Kronos deps. Run ON THE BOX before research/vast_run.sh.
set -euo pipefail

python3 -m pip install --upgrade pip
# cu128 wheel — supports RTX 5060 Ti (sm_120). If import fails, try cu129/nightly.
python3 -m pip install torch --index-url https://download.pytorch.org/whl/cu128
python3 -m pip install numpy pandas einops==0.8.1 "huggingface_hub>=0.33" \
    tqdm safetensors matplotlib

python3 - <<'EOF'
import torch
print(f"torch {torch.__version__} | cuda avail: {torch.cuda.is_available()} | "
      f"{torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU'}")
EOF
echo "setup done — now run: bash research/vast_run.sh"
