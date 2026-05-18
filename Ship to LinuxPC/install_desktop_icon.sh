#!/bin/bash
# Install desktop shortcut for Industry CAM Engine
#
# Run this once after copying files to the LinuxCNC machine:
#   chmod +x install_desktop_icon.sh
#   ./install_desktop_icon.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="$SCRIPT_DIR/industry-cam.desktop"
DESKTOP_DIR="$HOME/Desktop"

echo ""
echo "Installing Industry CAM Engine desktop shortcut..."
echo ""

# Copy to desktop
if [ -d "$DESKTOP_DIR" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_DIR/"
    chmod +x "$DESKTOP_DIR/industry-cam.desktop"
    # Mark as trusted (works on XFCE/Debian which LinuxCNC typically uses)
    if command -v gio &> /dev/null; then
        gio set "$DESKTOP_DIR/industry-cam.desktop" metadata::trusted true 2>/dev/null
    fi
    echo "✓ Desktop icon installed: $DESKTOP_DIR/industry-cam.desktop"
else
    echo "✗ Desktop directory not found at $DESKTOP_DIR"
    echo "  You can manually copy industry-cam.desktop to your desktop."
fi

# Install to applications menu
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
cp "$DESKTOP_FILE" "$APPS_DIR/"
echo "✓ Applications menu entry installed"

echo ""
echo "Done! You can now launch Industry CAM Engine from:"
echo "  • Desktop icon (double-click)"
echo "  • Applications menu (look under Manufacturing or Engineering)"
echo "  • Terminal:  linuxcnc /home/jacob/linuxcnc/configs/industry-cam/industry-cam.ini"
echo ""
echo "If the desktop icon doesn't launch on double-click:"
echo "  → Right-click the icon → 'Allow Launching' or 'Trust and Launch'"
echo ""
