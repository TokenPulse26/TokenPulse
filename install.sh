#!/usr/bin/env bash
set -euo pipefail

# TokenPulse Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/install.sh | bash

echo "Installing TokenPulse..."

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

# For now, only support macOS ARM (Apple Silicon)
if [ "$OS" != "darwin" ]; then
    echo "Error: TokenPulse currently only supports macOS. Linux support coming soon."
    exit 1
fi

# Create install directory
INSTALL_DIR="$HOME/.tokenpulse"
mkdir -p "$INSTALL_DIR"

# Download the latest release files from GitHub
REPO="TokenPulse26/TokenPulse"
BRANCH="main"
BASE_URL="https://raw.githubusercontent.com/$REPO/$BRANCH"

echo "Downloading proxy source..."
mkdir -p "$INSTALL_DIR/src-tauri/src"
curl -fsSL "$BASE_URL/src-tauri/src/proxy.rs" -o "$INSTALL_DIR/src-tauri/src/proxy.rs"
curl -fsSL "$BASE_URL/src-tauri/src/db.rs" -o "$INSTALL_DIR/src-tauri/src/db.rs"
curl -fsSL "$BASE_URL/src-tauri/src/lib.rs" -o "$INSTALL_DIR/src-tauri/src/lib.rs"
curl -fsSL "$BASE_URL/src-tauri/src/pricing.rs" -o "$INSTALL_DIR/src-tauri/src/pricing.rs"
curl -fsSL "$BASE_URL/src-tauri/src/main.rs" -o "$INSTALL_DIR/src-tauri/src/main.rs"
curl -fsSL "$BASE_URL/src-tauri/Cargo.toml" -o "$INSTALL_DIR/src-tauri/Cargo.toml"
curl -fsSL "$BASE_URL/src-tauri/pricing.json" -o "$INSTALL_DIR/src-tauri/pricing.json"
curl -fsSL "$BASE_URL/src-tauri/build.rs" -o "$INSTALL_DIR/src-tauri/build.rs"
curl -fsSL "$BASE_URL/src-tauri/tauri.conf.json" -o "$INSTALL_DIR/src-tauri/tauri.conf.json"

echo "Downloading dashboard..."
curl -fsSL "$BASE_URL/web-dashboard.py" -o "$INSTALL_DIR/web-dashboard.py"

echo "Downloading docs..."
curl -fsSL "$BASE_URL/GETTING_STARTED.md" -o "$INSTALL_DIR/GETTING_STARTED.md"
curl -fsSL "$BASE_URL/README.md" -o "$INSTALL_DIR/README.md"

# Check for Rust toolchain
if ! command -v cargo &> /dev/null; then
    echo ""
    echo "Rust toolchain not found. TokenPulse proxy requires Rust to build."
    echo "Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    echo ""
    echo "After installing Rust, run: cd $INSTALL_DIR/src-tauri && cargo build --release"
    echo "Then start the proxy: $INSTALL_DIR/src-tauri/target/release/tokenpulse"
    echo ""
else
    echo "Building proxy..."
    cd "$INSTALL_DIR/src-tauri"
    cargo build --release 2>&1 | tail -3

    # Copy binary to a convenient location
    cp target/release/tokenpulse "$INSTALL_DIR/tokenpulse" 2>/dev/null || true
    echo "✅ Proxy built: $INSTALL_DIR/tokenpulse"
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "⚠️  Python 3 not found. Install Python 3 to run the web dashboard."
else
    echo "✅ Python 3 found: $(python3 --version)"
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  TokenPulse installed to $INSTALL_DIR"
echo "═══════════════════════════════════════════"
echo ""
echo "  Start proxy:     $INSTALL_DIR/tokenpulse"
echo "  Start dashboard:  python3 $INSTALL_DIR/web-dashboard.py"
echo "  Dashboard URL:   http://localhost:4200"
echo ""
echo "  Point your AI tools at: http://localhost:4100"
echo ""
echo "  Full setup guide: $INSTALL_DIR/GETTING_STARTED.md"
echo "═══════════════════════════════════════════"
