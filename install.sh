#!/usr/bin/env bash
set -euo pipefail

# TokenPulse Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/install.sh | bash
#
# Flags (pass after `bash -s --` when piping, e.g.
#   curl -fsSL ... | bash -s -- --from-source
# ):
#   --from-source   Skip the pre-built binary path and build locally with cargo.

FROM_SOURCE=0
for arg in "$@"; do
    case "$arg" in
        --from-source)
            FROM_SOURCE=1
            ;;
        *)
            ;;
    esac
done

echo "Installing TokenPulse..."
echo "Note: this installer is currently a bootstrap helper for macOS Apple Silicon, not a polished general release installer."

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

# For now, only support macOS ARM (Apple Silicon)
if [ "$OS" != "darwin" ]; then
    echo "Error: TokenPulse currently only supports macOS. Linux support coming soon."
    exit 1
fi

case "$ARCH" in
    arm64|aarch64)
        ;;
    x86_64)
        echo "Error: TokenPulse currently supports Apple Silicon Macs only. This Mac reports architecture: $ARCH"
        exit 1
        ;;
    *)
        echo "Error: Unsupported architecture: $ARCH. TokenPulse currently supports Apple Silicon Macs only."
        exit 1
        ;;
esac

# Create install directory
INSTALL_DIR="$HOME/.tokenpulse"
mkdir -p "$INSTALL_DIR"

REPO="TokenPulse26/TokenPulse"
BRANCH="main"
BASE_URL="https://raw.githubusercontent.com/$REPO/$BRANCH"
API_URL="https://api.github.com/repos/$REPO/releases/latest"
BINARY_ASSET="tokenpulse-macos-arm64"
SHA_ASSET="tokenpulse-macos-arm64.sha256"

# Always pull the latest docs and dashboard, regardless of proxy install path
echo "Downloading dashboard..."
curl -fsSL "$BASE_URL/web-dashboard.py" -o "$INSTALL_DIR/web-dashboard.py"

echo "Downloading docs..."
curl -fsSL "$BASE_URL/GETTING_STARTED.md" -o "$INSTALL_DIR/GETTING_STARTED.md"
curl -fsSL "$BASE_URL/README.md" -o "$INSTALL_DIR/README.md"

install_from_release() {
    # Confirm a latest release exists via the GitHub API, then download assets
    # from the stable `/releases/latest/download/<name>` redirect URL. Parsing
    # the API payload with shell is fragile because GitHub returns it as a
    # single-line JSON blob; the redirect URL is the reliable contract.
    local api_status
    api_status=$(curl -sSL -o /dev/null -w '%{http_code}' -H "Accept: application/vnd.github+json" "$API_URL" 2>/dev/null || true)
    if [ "$api_status" != "200" ]; then
        if [ "$api_status" = "404" ]; then
            echo "No published release found for $REPO yet (API returned 404)."
        else
            echo "GitHub Releases API at $API_URL returned HTTP $api_status."
        fi
        return 1
    fi

    local bin_url="https://github.com/$REPO/releases/latest/download/$BINARY_ASSET"
    local sha_url="https://github.com/$REPO/releases/latest/download/$SHA_ASSET"

    echo "Downloading pre-built proxy binary from latest release..."
    echo "  binary:   $bin_url"
    echo "  checksum: $sha_url"

    local tmpdir
    tmpdir=$(mktemp -d)
    # shellcheck disable=SC2064
    # Clean up on function return AND on Ctrl-C / kill, otherwise an
    # interrupt between mktemp and the normal return path leaves the
    # tempdir behind.
    trap "rm -rf '$tmpdir'" RETURN INT TERM

    if ! curl -fsSL "$bin_url" -o "$tmpdir/$BINARY_ASSET"; then
        echo "Failed to download binary asset ($BINARY_ASSET) from latest release."
        return 1
    fi
    if ! curl -fsSL "$sha_url" -o "$tmpdir/$SHA_ASSET"; then
        echo "Failed to download checksum asset ($SHA_ASSET) from latest release."
        return 1
    fi

    echo "Verifying SHA256..."
    if ! ( cd "$tmpdir" && shasum -a 256 -c "$SHA_ASSET" ); then
        echo ""
        echo "Error: SHA256 verification failed for $BINARY_ASSET."
        echo "Refusing to install an unverified binary."
        return 2
    fi

    mv "$tmpdir/$BINARY_ASSET" "$INSTALL_DIR/tokenpulse"
    chmod +x "$INSTALL_DIR/tokenpulse"
    echo "✅ Proxy binary installed: $INSTALL_DIR/tokenpulse"
    return 0
}

install_from_source() {
    echo "Falling back to source build..."
    echo "Downloading proxy source..."
    mkdir -p "$INSTALL_DIR/src-tauri/src"
    curl -fsSL "$BASE_URL/src-tauri/src/proxy.rs" -o "$INSTALL_DIR/src-tauri/src/proxy.rs"
    curl -fsSL "$BASE_URL/src-tauri/src/db.rs" -o "$INSTALL_DIR/src-tauri/src/db.rs"
    curl -fsSL "$BASE_URL/src-tauri/src/lib.rs" -o "$INSTALL_DIR/src-tauri/src/lib.rs"
    curl -fsSL "$BASE_URL/src-tauri/src/pricing.rs" -o "$INSTALL_DIR/src-tauri/src/pricing.rs"
    curl -fsSL "$BASE_URL/src-tauri/src/main.rs" -o "$INSTALL_DIR/src-tauri/src/main.rs"
    curl -fsSL "$BASE_URL/src-tauri/Cargo.toml" -o "$INSTALL_DIR/src-tauri/Cargo.toml"
    curl -fsSL "$BASE_URL/src-tauri/Cargo.lock" -o "$INSTALL_DIR/src-tauri/Cargo.lock"
    curl -fsSL "$BASE_URL/src-tauri/pricing.json" -o "$INSTALL_DIR/src-tauri/pricing.json"
    curl -fsSL "$BASE_URL/src-tauri/build.rs" -o "$INSTALL_DIR/src-tauri/build.rs"
    curl -fsSL "$BASE_URL/src-tauri/tauri.conf.json" -o "$INSTALL_DIR/src-tauri/tauri.conf.json"

    if ! command -v cargo &> /dev/null; then
        echo ""
        echo "Rust toolchain not found. TokenPulse proxy requires Rust to build from source."
        echo "Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        echo ""
        echo "After installing Rust, run: cd $INSTALL_DIR/src-tauri && cargo build --release"
        echo "Then copy the binary:     cp $INSTALL_DIR/src-tauri/target/release/tokenpulse $INSTALL_DIR/tokenpulse"
        return 3
    fi

    echo "Building proxy (this can take several minutes)..."
    ( cd "$INSTALL_DIR/src-tauri" && cargo build --release 2>&1 | tail -3 )

    cp "$INSTALL_DIR/src-tauri/target/release/tokenpulse" "$INSTALL_DIR/tokenpulse"
    chmod +x "$INSTALL_DIR/tokenpulse"
    echo "✅ Proxy built from source: $INSTALL_DIR/tokenpulse"
    return 0
}

PROXY_OK=0

if [ "$FROM_SOURCE" = "1" ]; then
    echo "--from-source flag set: skipping pre-built binary."
    if install_from_source; then
        PROXY_OK=1
    fi
else
    if install_from_release; then
        PROXY_OK=1
    else
        rc=$?
        if [ "$rc" = "2" ]; then
            # Checksum mismatch is a hard fail — do not silently fall through to source build.
            echo ""
            echo "Aborting install because the downloaded binary failed SHA256 verification."
            echo "If you believe this is a mistake, re-run with:  install.sh --from-source"
            exit 2
        fi
        echo "Pre-built binary unavailable; falling back to source build."
        if install_from_source; then
            PROXY_OK=1
        fi
    fi
fi

# Check for Python 3 (dashboard runtime)
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
if [ "$PROXY_OK" = "1" ]; then
    echo "  Start proxy:     $INSTALL_DIR/tokenpulse"
else
    echo "  Proxy binary not yet available — see messages above to finish setup."
fi
echo "  Start dashboard: python3 $INSTALL_DIR/web-dashboard.py"
echo "  Dashboard URL:   http://127.0.0.1:4200"
echo ""
echo "  Point one AI tool at: http://127.0.0.1:4100"
echo ""
echo "  Full setup + verification guide: $INSTALL_DIR/GETTING_STARTED.md"
echo ""
echo "  First run on macOS:"
echo "    The binary is not codesigned for v1 early access. If macOS blocks it,"
echo "    open System Settings → Privacy & Security, scroll to the bottom, and"
echo "    click 'Allow Anyway' for tokenpulse. Then run it again."
echo "═══════════════════════════════════════════"
