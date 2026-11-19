#!/bin/bash
# Holy Grail replacement for gmag11/metatrader5_vnc's /Metatrader/start.sh
# (upstream: github.com/gmag11/MetaTrader5-Docker, MIT). Run by the image's KasmVNC
# autostart inside the desktop session, so Wine has a display.
#
# Changes vs upstream 2.3:
#   * pinned Wine-side Python packages (upstream installs unpinned mt5linux/rpyc at
#     every first start — today that resolves to mt5linux 1.1.x, whose server
#     entrypoint rejects the `-w` flag upstream passes, so RPyC never comes up);
#   * no Linux-side mt5linux at all: our allow-listed bridge (bridge_server.py)
#     runs directly under Wine Python, supervised by a restart loop;
#   * install steps are idempotent and logged to /config/holygrail-start.log.
set -u
exec > >(tee -a /config/holygrail-start.log) 2>&1

mt5file='/config/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe'
export WINEPREFIX='/config/.wine'
export WINEDEBUG='-all'
wine_executable="wine"
MT5_PY_VERSION="${MT5_PY_VERSION:-5.0.36}"   # MetaTrader5 pip package (Wine side)
RPYC_VERSION="${RPYC_VERSION:-6.0.2}"        # must match the bot image's rpyc
BRIDGE_PORT="${BRIDGE_PORT:-18812}"
MT5_CMD_OPTIONS="${MT5_CMD_OPTIONS:-}"
mono_url="https://dl.winehq.org/wine/wine-mono/10.3.0/wine-mono-10.3.0-x86.msi"
# 64-bit Python: terminal64 needs a 64-bit MetaTrader5 package, and the image's
# 32-bit Python crashes under Wine 11 (advapi32.SystemFunction036 unimplemented).
python_url="https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe"
py_unix="/config/.wine/drive_c/Program Files/Python39/python.exe"
py='C:\Program Files\Python39\python.exe'
mt5setup_url="https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"

log() { echo "[holygrail $(date -u +%FT%TZ)] $*"; }

# After a Wine upgrade the prefix keeps the old 32-bit DLLs until it is refreshed;
# without this, 32-bit programs (installers) abort on advapi32.SystemFunction036.
wine_ver="$($wine_executable --version)"
if [ "$(cat /config/.wine/.holygrail-wine-version 2>/dev/null)" != "$wine_ver" ]; then
    log "[0/6] Refreshing Wine prefix for $wine_ver..."
    wineboot -u
    echo "$wine_ver" > /config/.wine/.holygrail-wine-version
fi

if [ ! -e "/config/.wine/drive_c/windows/mono" ]; then
    log "[1/6] Installing Mono..."
    mkdir -p /config/.wine/drive_c
    curl -fsSL -o /config/.wine/drive_c/mono.msi "$mono_url"
    WINEDLLOVERRIDES=mscoree=d $wine_executable msiexec /i /config/.wine/drive_c/mono.msi /qn
    rm -f /config/.wine/drive_c/mono.msi
fi

if [ ! -e "$mt5file" ]; then
    log "[2/6] Installing MetaTrader 5..."
    $wine_executable reg add "HKEY_CURRENT_USER\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f
    curl -fsSL -o /config/.wine/drive_c/mt5setup.exe "$mt5setup_url"
    $wine_executable "/config/.wine/drive_c/mt5setup.exe" "/auto" &
    wait
    rm -f /config/.wine/drive_c/mt5setup.exe
fi

if [ -e "$mt5file" ]; then
    log "[3/6] Starting MetaTrader 5 terminal..."
    # shellcheck disable=SC2086
    $wine_executable "$mt5file" $MT5_CMD_OPTIONS &
else
    log "[3/6] MetaTrader 5 is NOT installed — check the log above."
fi

if [ ! -e "$py_unix" ]; then
    log "[4/6] Installing Python 3.9 (64-bit) in Wine..."
    curl -fsSL "$python_url" -o /tmp/python-installer.exe
    $wine_executable /tmp/python-installer.exe /quiet InstallAllUsers=1 PrependPath=1
    rm -f /tmp/python-installer.exe
fi

log "[5/6] Ensuring Wine Python packages (MetaTrader5==$MT5_PY_VERSION, rpyc==$RPYC_VERSION)..."
if ! $wine_executable "$py" -c "import MetaTrader5, rpyc, sys; \
sys.exit(0 if (MetaTrader5.__version__.startswith('$MT5_PY_VERSION') and rpyc.__version__ == '$RPYC_VERSION') else 1)" >/dev/null 2>&1; then
    # numpy<2: MT5 5.0.36 is built against numpy 1.x; force-reinstall repairs a
    # half-upgraded numpy left by an earlier unpinned install.
    $wine_executable "$py" -m pip install --no-cache-dir --disable-pip-version-check \
        --force-reinstall "MetaTrader5==$MT5_PY_VERSION" "rpyc==$RPYC_VERSION" "numpy<2"
fi

# Copy the bridge into the prefix (Wine Python reads Windows paths more reliably).
cp /Metatrader/bridge_server.py /config/.wine/drive_c/bridge_server.py

log "[6/6] Starting MT5 bridge on :$BRIDGE_PORT (restart loop)..."
(
    while true; do
        $wine_executable "$py" 'C:\bridge_server.py' "$BRIDGE_PORT"
        log "bridge exited ($?) — restarting in 5s"
        sleep 5
    done
) &
