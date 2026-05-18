#!/bin/bash
# Launch the Industry CAM Engine GUI for LinuxCNC
# This script is referenced by DISPLAY in industry-cam.ini

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/gui/main_window.py" "$@"
