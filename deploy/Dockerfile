# Holy Grail bot (Linux). Talks to the MT5 terminal in the `mt5` service over the
# RPyC bridge (providers/mt5_bridge.py). Build context = repo root:
#   docker compose -f deploy/docker-compose.yml build
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/model/Kronos \
    KRONOS_PATH=/app/model/Kronos \
    HF_HOME=/hf-cache

WORKDIR /app

# CPU-only torch first (the default wheel pulls ~2 GB of CUDA).
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.13.0"

COPY requirements.txt /tmp/requirements.txt
# rpyc must match RPYC_VERSION in deploy/mt5/start.sh (Wine side).
RUN pip install -r /tmp/requirements.txt "rpyc==6.0.2"

COPY . /app

RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /hf-cache /app/data \
    && chown -R bot:bot /hf-cache /app/data
USER bot

CMD ["python", "-m", "soldier.loop", "--interval", "300"]
