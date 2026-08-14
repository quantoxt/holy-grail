-- The measurement loop: every Kronos prediction (traded OR skipped/HOLD) gets a
-- row at signal time and is resolved ~2h later against the actual close.
-- This is where per-symbol accuracy, N-sample comparison and confidence
-- calibration come from — the bot stops flying blind on its own edge.
create table if not exists prediction_evaluations (
  id bigint generated always as identity primary key,
  symbol text not null,
  timeframe text,
  signal_time timestamptz not null default now(),
  due_time timestamptz not null,
  direction text not null,             -- BUY / SELL / HOLD (all are scored)
  predicted_move double precision,
  predicted_close double precision,
  current_close double precision,
  confidence double precision,
  snr double precision,
  sample_count int,
  outcome text,                        -- hit / miss / flat (null until resolved)
  actual_close double precision,
  actual_move double precision,
  resolved_at timestamptz
);
create index if not exists idx_pred_eval_due on prediction_evaluations (due_time) where outcome is null;
create index if not exists idx_pred_eval_resolved on prediction_evaluations (resolved_at desc);
GRANT ALL ON prediction_evaluations TO service_role, anon, authenticated;
GRANT ALL ON SEQUENCE prediction_evaluations_id_seq TO service_role, anon, authenticated;
