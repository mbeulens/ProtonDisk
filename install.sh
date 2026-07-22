#!/usr/bin/env bash
# Install ProtonDisk for the current user, from this checkout:
#   - a Python venv (system PyGObject/GTK + fusepy)
#   - a `protondisk` command on your PATH
#   - the GUI application entry
#   - a systemd user service that auto-mounts ~/ProtonDisk at login
#
# Idempotent — re-run to update after pulling new code.
set -euo pipefail

REPO="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
VENV="$REPO/.venv-gui"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
UNIT_DIR="$HOME/.config/systemd/user"
MOUNTPOINT="$HOME/ProtonDisk"

echo "ProtonDisk installer"
echo "  repo: $REPO"

# 1. venv (system-site-packages so it can see system PyGObject/GTK4/libadwaita)
if [ ! -x "$VENV/bin/python" ]; then
    echo "· creating venv ($VENV) …"
    python3 -m venv --system-site-packages "$VENV"
fi
echo "· installing package + dependencies …"
"$VENV/bin/pip" install -q --upgrade pip >/dev/null
"$VENV/bin/pip" install -q -e "$REPO" fusepy

# 2. make the launchers executable
chmod +x "$REPO/scripts/protondisk-gui" "$REPO/scripts/protondisk-mount" \
         "$REPO/scripts/protondisk-mount-daemon"

# 3. `protondisk` command on PATH
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/protondisk" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" -m protondisk.cli "\$@"
EOF
chmod +x "$BIN_DIR/protondisk"
echo "· command:     $BIN_DIR/protondisk"
case ":$PATH:" in
    *":$BIN_DIR:"*) : ;;
    *) echo "               (add $BIN_DIR to your PATH to run 'protondisk' directly)" ;;
esac

# 4. GUI application entry
mkdir -p "$APPS_DIR"
sed "s|@REPO@|$REPO|g" "$REPO/packaging/protondisk.desktop.in" > "$APPS_DIR/protondisk.desktop"
chmod +x "$APPS_DIR/protondisk.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" 2>/dev/null || true
echo "· app entry:   $APPS_DIR/protondisk.desktop"

# 5. systemd user service — auto-mount ~/ProtonDisk at login
mkdir -p "$UNIT_DIR"
sed "s|@REPO@|$REPO|g" "$REPO/packaging/protondisk-mount.service.in" > "$UNIT_DIR/protondisk-mount.service"
systemctl --user daemon-reload
systemctl --user enable --now protondisk-mount.service >/dev/null 2>&1 || true
echo "· service:     protondisk-mount.service (mounts $MOUNTPOINT at login)"

echo
echo "Done."
echo "  • Not signed in yet?      protondisk auth login  &&  systemctl --user restart protondisk-mount.service"
echo "  • Your Drive:             $MOUNTPOINT"
echo "  • Mount status:           systemctl --user status protondisk-mount.service"
echo "  • GUI:                    search \"ProtonDisk\" in your app launcher"
echo "  • Uninstall:              $REPO/uninstall.sh"
