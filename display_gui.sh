#!/bin/bash
# display_gui.sh — Called by LinuxCNC as the DISPLAY program
#
# This script is referenced in industry-cam.ini:
#   DISPLAY = /home/jacob/linuxcnc/configs/industry-cam/display_gui.sh
#
# At this point LinuxCNC is already running (realtime loaded, HAL active).
# We just need to start the Python GUI which connects to LinuxCNC via its API.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
exec python3 "$SCRIPT_DIR/gui/main_window.py" "$@"
