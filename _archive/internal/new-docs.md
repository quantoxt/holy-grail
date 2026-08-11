# Notes: "Re(Visiting) Time Series Foundation Models in Finance"

**Author:** Eghbal Rahimikia
**Source:** FoFI 2026 working paper, Lancaster University
**Link:** http://wp.lancs.ac.uk/fofi2026/files/2026/03/FoFI-2026-020-Eghbal-Rahimikia.pdf

## Core Setup
- Large-scale dataset of daily excess returns across global markets.
- Compares three regimes: zero-shot inference, fine-tuning a pretrained TSFM, and pretraining a TSFM from scratch on financial data.
- Benchmarks against strong non-TSFM baselines (Lasso, Ridge, NN, CatBoost, XGBoost, LightGBM).

## Key Findings (most relevant to your case)
1. **Off-the-shelf pretrained TSFMs perform poorly** in both zero-shot and fine-tuned settings when applied to financial return series.
2. **Pretraining from scratch on financial data** (rather than fine-tuning a generic pretrained model) produces substantial gains in both forecasting accuracy and economic performance metrics (risk-adjusted portfolio returns).
3. **Synthetic data augmentation helps, but only as a supplement** — the paper frames it as one of three levers (alongside dataset scale and hyperparameter tuning) that further improve an already financially-pretrained model. It's not treated as a substitute for real financial pretraining data.
4. When combined with financial factors, synthetic augmentation + TSFMs showed consistent improvements in both statistical accuracy and portfolio-level outcomes.
5. Best reported result: Chronos (small) hit ~51.74% directional accuracy vs. 51.16% for CatBoost at a 512-length window — a narrow edge, illustrating how hard this task is even for a well-set-up model.
6. Expanding from US-only to global training data helped some baseline models' R² but weakened directional accuracy and portfolio performance for most models — bigger/more diverse data isn't automatically better for this task.

## Why this might matter for your Kronos retrain
- Your synthetic-only, 3-month, single-pair (v_75_5m) fine-tune is a small, narrow slice of data — this paper's results suggest that's roughly the failure mode to expect: synthetic augmentation on top of a financially-pretrained base helps, but synthetic data alone, especially limited in scope, doesn't substitute for broad real financial pretraining.
- Kronos was already pretrained on 12B+ real K-line records — your fine-tune is a small perturbation on top of that. If the synthetic distribution (of v_75_5m specifically) is narrow or unlike Kronos's original pretraining distribution, you may be pulling the model away from useful priors rather than adapting it.
- Worth testing: fine-tune on a broader/more diverse synthetic set, or mix real + synthetic data, rather than pure synthetic on one narrow instrument/timeframe.

---
*Compiled from search snippets — read the full PDF at the link above for methodology details, full tables, and robustness checks.*