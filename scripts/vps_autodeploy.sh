#!/usr/bin/env bash
# vps_autodeploy.sh — unattended bot deploy for the holy-grail Linux VPS.
#
# Runs as `opencode-deploy` from its own crontab (every 5 min):
#   */5 * * * * /opt/holy-grail/scripts/vps_autodeploy.sh >> /home/opencode-deploy/autodeploy.log 2>&1
#
# What it does: polls GitHub main, and when a NEW commit appears whose diff
# touches bot-relevant paths, rsyncs the code into /opt/holy-grail (same
# excludes as the manual flow) and rebuilds/restarts ONLY via the blessed
# `sudo holygrail-deploy bot` subcommand. No git checkout lives on the VPS;
# state is a single SHA file in the agent's home.
#
# Hard limits (mirror the VPS hand-off rules):
#   - NEVER touches the mt5 service directly, never rebuilds/reboots the VPS.
#   - NEVER writes deploy/ (root-owned) or reads .env — both are excluded.
#   - deploy/ and supabase/migrations/ changes are LOGGED LOUDLY for a human;
#     code still ships, state still advances (blind spots are worse than lag).
#
# Env overrides: REPO_URL, BRANCH, APP_DIR, STATE_FILE, DRY_RUN=1 (log only).
set -u
REPO_URL="${REPO_URL:-https://github.com/quantoxt/holy-grail.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/holy-grail}"
STATE_FILE="${STATE_FILE:-$HOME/.holygrail-autodeploy.sha}"
LOCK_FILE="${LOCK_FILE:-$HOME/.holygrail-autodeploy.lock}"

log() { echo "$(date -u +%FT%TZ) autodeploy: $*"; }

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "previous run still active, skipping"
    exit 0
fi

# --- 1. what's new on GitHub? (public repo: no auth needed) ---
remote_sha="$(git ls-remote "$REPO_URL" "$BRANCH" 2>/dev/null | awk '{print $1}')"
if [ -z "$remote_sha" ]; then
    log "git ls-remote failed (network?), will retry next tick"
    exit 0
fi
last_sha=""
[ -f "$STATE_FILE" ] && last_sha="$(cat "$STATE_FILE" 2>/dev/null)"
if [ "$remote_sha" = "$last_sha" ]; then
    exit 0  # nothing new — stay silent
fi
log "new commit: ${last_sha:-(none)} -> $remote_sha"

# --- 2. fetch it into a scratch clone ---
work="$(mktemp -d "${TMPDIR:-/tmp}/hg-deploy.XXXXXX")"
cleanup() { rm -rf "$work"; }
trap cleanup EXIT
if ! git clone --quiet --depth 100 --branch "$BRANCH" "$REPO_URL" "$work/repo" 2>/dev/null; then
    log "clone failed, will retry next tick"
    exit 0
fi

# --- 3. classify the diff (skip bot-irrelevant pushes like frontend-only) ---
changed=""
if [ -n "$last_sha" ]; then
    if ! git -C "$work/repo" cat-file -e "$last_sha" 2>/dev/null; then
        git -C "$work/repo" fetch --quiet --deepen=500 origin "$BRANCH" 2>/dev/null || true
    fi
    if git -C "$work/repo" cat-file -e "$last_sha" 2>/dev/null; then
        changed="$(git -C "$work/repo" diff --name-only "$last_sha" "$remote_sha" 2>/dev/null || true)"
    fi
fi
if [ -n "$last_sha" ] && [ -n "$changed" ]; then
    relevant="$(echo "$changed" | grep -v -E '^(frontend/|\.claude/|.+\.md$)' || true)"
    if [ -z "$relevant" ]; then
        log "only bot-irrelevant files changed ($(echo "$changed" | tr '\n' ' ')), skipping rebuild"
        [ "${DRY_RUN:-0}" = "1" ] || echo "$remote_sha" > "$STATE_FILE"
        exit 0
    fi
    echo "$changed" | grep -E '^deploy/' >/dev/null && \
        log "WARNING: deploy/ changed — NOT synced (root-owned, needs a human): $(echo "$changed" | grep -E '^deploy/' | tr '\n' ' ')"
    echo "$changed" | grep -E '^supabase/migrations/' >/dev/null && \
        log "WARNING: new migration(s) — apply manually (supabase db push): $(echo "$changed" | grep -E '^supabase/migrations/' | tr '\n' ' ')"
else
    log "no baseline diff available (first run or shallow history) — deploying full tree"
fi

if [ "${DRY_RUN:-0}" = "1" ]; then
    log "DRY_RUN: would rsync $remote_sha -> $APP_DIR and run 'sudo holygrail-deploy bot'"
    exit 0
fi

# --- 4. sync code (same excludes as the manual flow; never .env, never deploy/) ---
if ! rsync -az --delete-excluded \
    --exclude .git --exclude .env --exclude deploy/ \
    --exclude venv-torch/ --exclude frontend/node_modules/ \
    --exclude frontend/dist/ --exclude model/ \
    "$work/repo/" "$APP_DIR/"; then
    log "ERROR: rsync failed — state untouched, will retry"
    exit 1
fi

# --- 5. rebuild + restart the bot container ---
if ! sudo -n holygrail-deploy bot; then
    log "ERROR: holygrail-deploy bot failed — state untouched, will retry (code is synced, container is stale)"
    exit 1
fi

# --- 6. sanity: bot container up? ---
if sudo -n holygrail-deploy ps 2>/dev/null | grep -q "holygrail-bot-1.*Up"; then
    echo "$remote_sha" > "$STATE_FILE"
    log "deployed $remote_sha, bot Up"
    exit 0
else
    log "ERROR: bot container not Up after deploy — state untouched, will retry"
    exit 1
fi
