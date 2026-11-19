# MT5 terminal under Wine + KasmVNC desktop + Holy Grail's allow-listed RPyC bridge.
# Base: gmag11/metatrader5_vnc (linuxserver baseimage-kasmvnc:debianbookworm,
# winehq-stable). Pinned to tag 2.3 (pushed 2025-12-20, == latest at time of writing).
# Note: pinning the image does NOT pin the MT5 terminal — it self-updates in /config.
FROM gmag11/metatrader5_vnc:2.3

# The base ships Wine 10.0, which trips MT5's anti-debug check ("A debugger has been
# found running in your system" — Wine bugs 57950/59352; late Wine 10 / early Wine 11).
# Reports (mql5 forum 503128, Apr 2026) have current MT5 builds running on Wine 11.6+.
# Newest Wine 11 on Debian 12 with an i386 build is winehq-devel 11.10; installing it replaces winehq-stable.
ARG WINE_VERSION=11.10~bookworm-1
RUN curl -fsSL https://dl.winehq.org/wine-builds/winehq.key -o /etc/apt/keyrings/winehq-archive.key \
 && apt-get update \
 && apt-get install -y --install-recommends \
      winehq-devel=${WINE_VERSION} wine-devel=${WINE_VERSION} \
      wine-devel-amd64=${WINE_VERSION} wine-devel-i386:i386=${WINE_VERSION} \
 && rm -rf /var/lib/apt/lists/* \
 && wine --version

COPY deploy/mt5/start.sh /Metatrader/start.sh
COPY deploy/mt5/bridge_server.py /Metatrader/bridge_server.py
RUN chmod +x /Metatrader/start.sh
