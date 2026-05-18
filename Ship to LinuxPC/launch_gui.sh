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

# Check if linuxcnc command exists and Mesa board is reachable
if command -v linuxcnc &> /dev/null && ping -c 1 -W 1 192.168.1.121 &> /dev/null; then
    # Full machine mode — LinuxCNC starts realtime, loads HAL, then launches GUI
    exec linuxcnc "$INI_FILE"
else
    # Offline mode — just the GUI with mock backend
    echo "================================================"
    echo "  OFFLINE MODE — Mesa board not detected"
    echo "  GUI will use simulated data"
    echo "================================================"
    cd "$SCRIPT_DIR"
    exec python3 -m gui.main_window
fi
