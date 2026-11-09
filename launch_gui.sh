#!/bin/bash
# Launch Industry CAM Engine — Smart Launcher
#
# ONE ICON, TWO MODES:
#   - If LinuxCNC is installed AND Mesa board is reachable → full machine mode
#   - Otherwise → offline/preview mode (GUI only, simulated data)
#
# This is what the desktop icon calls.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INI_FILE="$SCRIPT_DIR/industry-cam.ini"

MESA_IP="192.168.1.121"
MESA_WAIT_S=10   # the card can take a few seconds to answer after power-up

mesa_up() { ping -c 1 -W 1 "$MESA_IP" &> /dev/null; }

if command -v linuxcnc &> /dev/null; then
    # Wait up to MESA_WAIT_S for the Mesa card instead of a single ping, so a
    # quick power-on-and-launch does not silently land in offline mode
    # (2026-11-08: offline mode started with no tool table, mistaken for live).
    echo "Waiting for Mesa card at $MESA_IP (up to ${MESA_WAIT_S}s)..."
    start=$SECONDS
    while (( SECONDS - start < MESA_WAIT_S )); do
        if mesa_up; then
            # Full machine mode — LinuxCNC starts realtime, loads HAL, then launches GUI
            exec linuxcnc "$INI_FILE"
        fi
        sleep 0.5          # ping itself waits up to 1 s when the card is silent
    done
    OFFLINE_REASON="Mesa card not found at $MESA_IP after ${MESA_WAIT_S} s"
else
    OFFLINE_REASON="LinuxCNC is not installed on this computer"
fi

# Offline mode — just the GUI with mock backend
echo "================================================"
echo "  OFFLINE MODE — $OFFLINE_REASON"
echo "  GUI will use simulated data"
echo "================================================"
export INDUSTRY_CAM_OFFLINE_REASON="$OFFLINE_REASON"
cd "$SCRIPT_DIR"
exec python3 -m gui.main_window
