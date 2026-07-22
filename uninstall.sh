#!/usr/bin/env bash
# Remove the ProtonDisk user integration (service, command, app entry).
# Keeps the repo checkout and its .venv-gui — delete those yourself if you want.
set -euo pipefail

BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
UNIT_DIR="$HOME/.config/systemd/user"
MOUNTPOINT="$HOME/ProtonDisk"

echo "· stopping + disabling the mount service …"
systemctl --user disable --now protondisk-mount.service >/dev/null 2>&1 || true
fusermount3 -uz "$MOUNTPOINT" 2>/dev/null || fusermount -uz "$MOUNTPOINT" 2>/dev/null || true
rm -f "$UNIT_DIR/protondisk-mount.service"
systemctl --user daemon-reload >/dev/null 2>&1 || true

echo "· removing command + app entry …"
rm -f "$BIN_DIR/protondisk"
rm -f "$APPS_DIR/protondisk.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo
echo "Uninstalled the ProtonDisk user integration."
echo "  (Kept the repo and .venv-gui. Remove $MOUNTPOINT yourself if you want the empty mount dir gone.)"
