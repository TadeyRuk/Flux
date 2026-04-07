#!/bin/bash
set -e

APP_DIR="$HOME/.local/share/flux"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Flux..."

# Remove old power-control install if present
rm -f "$BIN_DIR/power-control"
rm -f "$DESKTOP_DIR/power-control.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/power-control.svg"

# Copy app files
mkdir -p "$APP_DIR"
cp -r "$SRC_DIR/src/"* "$APP_DIR/"

# Create executable wrapper
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/flux" << EOF
#!/bin/bash
cd "$APP_DIR"
exec python3 "$APP_DIR/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/flux"

# Install SVG icon (copy from project root)
mkdir -p "$ICON_DIR"
cp "$SRC_DIR/flux.svg" "$ICON_DIR/flux.svg"

# Install .desktop file
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/com.flux.app.desktop" << EOF
[Desktop Entry]
Name=Flux
Comment=Fan curves, power profiles and GPU management
Exec=$BIN_DIR/flux
Icon=flux
Terminal=false
Type=Application
Categories=System;Settings;HardwareSettings;
Keywords=fan;power;gpu;thermal;asus;flux;
StartupNotify=true
EOF

# Update icon cache and desktop database
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo ""
echo "Done! Flux installed."
echo ""
echo "  Launch from terminal:   flux"
echo "  Launch from app grid:   search 'Flux'"
echo ""
echo "Make sure ~/.local/bin is in your PATH."
echo "If not, add to ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
