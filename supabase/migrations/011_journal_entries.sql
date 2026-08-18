-- Journal entries — manually editable from the dashboard (Journal view).
-- Tracks the days the bot completed the weekly goal + free notes per day.
-- The goal-banked days themselves come from risk_events (auto); this table is
-- the user-authored layer: notes, tags, and manual milestone records.
create table if not exists journal_entries (
  id bigint generated always as identity primary key,
  entry_date date not null,
  title text not null default '',
  note text not null default '',
  tags text not null default '',           -- comma-separated, e.g. "goal,scalp-fix"
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists idx_journal_date on journal_entries (entry_date);
create index if not exists idx_journal_updated on journal_entries (updated_at desc);
GRANT ALL ON journal_entries TO service_role, anon, authenticated;
GRANT ALL ON SEQUENCE journal_entries_id_seq TO service_role, anon, authenticated;
