#!/usr/bin/env bash
set -euo pipefail

# TokenPulse Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/install.sh | bash
#
# Flags (pass after `bash -s --` when piping, e.g.
#   curl -fsSL ... | bash -s -- --from-source
# ):
#   --from-source    Skip the pre-built binary path and build locally with cargo.
#   --no-autostart   Skip launchd install + auto-start. You'll start services manually.

FROM_SOURCE=0
NO_AUTOSTART=0
for arg in "$@"; do
    case "$arg" in
        --from-source)
            FROM_SOURCE=1
            ;;
        --no-autostart)
            NO_AUTOSTART=1
            ;;
        *)
            ;;
    esac
done

echo "Installing TokenPulse..."
echo "Note: this early-access installer supports macOS Apple Silicon and auto-starts TokenPulse by default."

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

# ── Pre-flight checks ──────────────────────────────────────────────────────────
preflight_checks() {
    local failed=0

    # 1. curl present (critical for downloads)
    if ! command -v curl &>/dev/null; then
        echo "❌ curl not found. Cannot download TokenPulse."
        failed=1
    fi

    # 2. Write permission on \$HOME
    if mkdir -p "$HOME/.tokenpulse/.preflight-test" 2>/dev/null && rm -rf "$HOME/.tokenpulse/.preflight-test"; then
        : # ok
    else
        echo "❌ Cannot write to $HOME/.tokenpulse/ — check filesystem permissions."
        failed=1
    fi

    # 3. Python 3 (warn only — dashboard needs it, proxy doesn't)
    if ! command -v python3 &>/dev/null; then
        echo "⚠️  Python 3 not found. The proxy will install, but the dashboard requires Python 3."
    fi

    # 4. Disk space — at least 50 MB free on the volume containing \$HOME
    local avail_kb
    avail_kb=$(df -k "$HOME" 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$avail_kb" ] && [ "$avail_kb" -lt 51200 ] 2>/dev/null; then
        echo "⚠️  Low disk space ($(( avail_kb / 1024 )) MB free). TokenPulse needs ~50 MB."
    fi

    # 5. Network connectivity
    local http_code
    http_code=$(curl -fsSL -o /dev/null -w '%{http_code}' --connect-timeout 5 https://api.github.com 2>/dev/null || true)
    if [ "$http_code" != "200" ]; then
        echo "❌ No network connectivity — cannot download TokenPulse."
        failed=1
    fi

    if [ "$failed" -ne 0 ]; then
        echo ""
        echo "Pre-flight checks failed. Fix the issues above and re-run."
        exit 1
    fi
}

preflight_checks

# Create install directory
INSTALL_DIR="$HOME/.tokenpulse"
LOG_DIR="$INSTALL_DIR/logs"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PROXY_LABEL="com.tokenpulse.proxy"
DASHBOARD_LABEL="com.tokenpulse.dashboard"
PROXY_PLIST="$LAUNCH_AGENTS_DIR/$PROXY_LABEL.plist"
DASHBOARD_PLIST="$LAUNCH_AGENTS_DIR/$DASHBOARD_LABEL.plist"

mkdir -p "$INSTALL_DIR"
mkdir -p "$LOG_DIR"

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

# Detect Python 3 (dashboard runtime) with a preference order
detect_python3() {
    # Prefer Homebrew on Apple Silicon, then system /usr/bin/python3, then PATH lookup.
    local candidates=(
        "/opt/homebrew/bin/python3"
        "/usr/local/bin/python3"
        "/usr/bin/python3"
    )
    for c in "${candidates[@]}"; do
        if [ -x "$c" ]; then
            echo "$c"
            return 0
        fi
    done
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return 0
    fi
    return 1
}

PYTHON3_PATH=""
if PYTHON3_PATH=$(detect_python3); then
    echo "✅ Python 3 found: $PYTHON3_PATH ($($PYTHON3_PATH --version 2>&1))"
else
    echo "⚠️  Python 3 not found. Install Python 3 to run the web dashboard."
fi

# --- launchd / autostart ---

# Port collision preflight: make sure nothing else is already bound to 4100/4200
# (unless it's an existing TokenPulse service we're about to replace).
port_owner_pid() {
    # Returns the PID bound to the given TCP port, or empty if none.
    local port="$1"
    lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n1 || true
}

port_owner_command() {
    local pid="$1"
    if [ -z "$pid" ]; then
        return 0
    fi
    ps -o comm= -p "$pid" 2>/dev/null | tr -d ' ' || true
}

is_existing_tokenpulse_service() {
    # Return 0 if the given Label is currently loaded in this user's launchd domain.
    local label="$1"
    launchctl list 2>/dev/null | awk '{print $3}' | grep -Fxq "$label"
}

unload_service() {
    # Best-effort unload. Prefer `bootout` on modern macOS, fall back to `unload`.
    local label="$1"
    local plist="$2"
    if is_existing_tokenpulse_service "$label"; then
        launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || launchctl unload "$plist" 2>/dev/null || true
    else
        # Even if not listed, try unload on the file in case it's partially registered.
        if [ -f "$plist" ]; then
            launchctl unload "$plist" 2>/dev/null || true
        fi
    fi
}

load_service() {
    # Prefer modern `bootstrap`; fall back to `load` if bootstrap fails.
    local plist="$1"
    if launchctl bootstrap "gui/$(id -u)" "$plist" 2>/dev/null; then
        return 0
    fi
    launchctl load "$plist" 2>/dev/null
}

write_proxy_plist() {
    cat > "$PROXY_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PROXY_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/tokenpulse</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/proxy.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/proxy.error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
EOF
}

write_dashboard_plist() {
    local py="$1"
    cat > "$DASHBOARD_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$DASHBOARD_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$py</string>
        <string>$INSTALL_DIR/web-dashboard.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/dashboard.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/dashboard.error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
EOF
}

wait_for_health() {
    local url="$1"
    local label="$2"
    local tries=30  # 30 * 0.5s = ~15s
    local i=0
    while [ "$i" -lt "$tries" ]; do
        if curl -fsSL -o /dev/null -m 2 "$url" 2>/dev/null; then
            echo "✅ $label healthy at $url"
            return 0
        fi
        i=$((i + 1))
        sleep 0.5
    done
    echo "❌ $label did not become healthy at $url within 15s"
    return 1
}

install_launchd_services() {
    # Idempotent-safe: unload existing agents with same Label (if any),
    # write fresh plists pointing at $HOME/.tokenpulse/, then bootstrap them.
    mkdir -p "$LAUNCH_AGENTS_DIR"

    # Detect pre-existing services and warn before replacing — but proceed.
    local replacing=0
    if is_existing_tokenpulse_service "$PROXY_LABEL" || is_existing_tokenpulse_service "$DASHBOARD_LABEL"; then
        replacing=1
    fi
    if [ "$replacing" = "1" ]; then
        echo ""
        echo "Note: replacing existing com.tokenpulse.proxy / com.tokenpulse.dashboard launchd"
        echo "      services with user-install versions pointing at $INSTALL_DIR."
    fi

    # Port collision preflight. Allowed occupant = an existing TokenPulse service we're replacing.
    local proxy_pid dash_pid
    proxy_pid=$(port_owner_pid 4100)
    dash_pid=$(port_owner_pid 4200)

    # If a port is occupied and we're NOT about to replace a tokenpulse service, that's a hard fail.
    if [ -n "$proxy_pid" ] && ! is_existing_tokenpulse_service "$PROXY_LABEL"; then
        local cmd
        cmd=$(port_owner_command "$proxy_pid")
        echo ""
        echo "❌ Port 4100 is already in use by PID $proxy_pid ($cmd)."
        echo "   TokenPulse needs port 4100 for the proxy."
        echo "   Stop the other process or pass --no-autostart to skip the launchd step."
        return 1
    fi
    if [ -n "$dash_pid" ] && ! is_existing_tokenpulse_service "$DASHBOARD_LABEL"; then
        local cmd
        cmd=$(port_owner_command "$dash_pid")
        echo ""
        echo "❌ Port 4200 is already in use by PID $dash_pid ($cmd)."
        echo "   TokenPulse needs port 4200 for the web dashboard."
        echo "   Stop the other process or pass --no-autostart to skip the launchd step."
        return 1
    fi

    echo "Installing launchd services..."

    # Unload old definitions first so we can atomically replace the plist files.
    unload_service "$PROXY_LABEL" "$PROXY_PLIST"
    unload_service "$DASHBOARD_LABEL" "$DASHBOARD_PLIST"

    # Small grace period so ports release before we relaunch.
    sleep 1

    write_proxy_plist
    if [ -n "$PYTHON3_PATH" ]; then
        write_dashboard_plist "$PYTHON3_PATH"
    else
        echo "⚠️  Skipping dashboard launchd service (no python3 detected)."
    fi

    # Load the proxy
    if ! load_service "$PROXY_PLIST"; then
        echo "❌ Failed to load $PROXY_LABEL via launchctl."
        return 1
    fi

    # Load the dashboard (if plist was written)
    if [ -f "$DASHBOARD_PLIST" ] && [ -n "$PYTHON3_PATH" ]; then
        if ! load_service "$DASHBOARD_PLIST"; then
            echo "❌ Failed to load $DASHBOARD_LABEL via launchctl."
            return 1
        fi
    fi

    # Health checks
    if ! wait_for_health "http://127.0.0.1:4100/health" "proxy"; then
        echo ""
        echo "--- tail of $LOG_DIR/proxy.error.log ---"
        tail -n 40 "$LOG_DIR/proxy.error.log" 2>/dev/null || echo "(no log yet)"
        echo "--- tail of $LOG_DIR/proxy.log ---"
        tail -n 40 "$LOG_DIR/proxy.log" 2>/dev/null || echo "(no log yet)"
        echo "--- launchctl print ---"
        launchctl print "gui/$(id -u)/$PROXY_LABEL" 2>&1 | head -n 40 || true
        return 1
    fi

    if [ -n "$PYTHON3_PATH" ]; then
        if ! wait_for_health "http://127.0.0.1:4200/" "dashboard"; then
            echo ""
            echo "--- tail of $LOG_DIR/dashboard.error.log ---"
            tail -n 40 "$LOG_DIR/dashboard.error.log" 2>/dev/null || echo "(no log yet)"
            echo "--- tail of $LOG_DIR/dashboard.log ---"
            tail -n 40 "$LOG_DIR/dashboard.log" 2>/dev/null || echo "(no log yet)"
            echo "--- launchctl print ---"
            launchctl print "gui/$(id -u)/$DASHBOARD_LABEL" 2>&1 | head -n 40 || true
            return 1
        fi
    fi

    return 0
}

RUNNING=0
if [ "$PROXY_OK" = "1" ] && [ "$NO_AUTOSTART" = "0" ]; then
    if install_launchd_services; then
        RUNNING=1
    else
        echo ""
        echo "❌ Auto-start failed. TokenPulse is installed but not running."
        echo "   You can retry by re-running install.sh, or start manually:"
        echo "     $INSTALL_DIR/tokenpulse"
        if [ -n "$PYTHON3_PATH" ]; then
            echo "     $PYTHON3_PATH $INSTALL_DIR/web-dashboard.py"
        fi
        exit 1
    fi
fi

echo ""
echo "═══════════════════════════════════════════"
if [ "$RUNNING" = "1" ]; then
    echo "  🟢 TokenPulse is running"
    echo "═══════════════════════════════════════════"
    echo ""
    echo "  Dashboard:     http://127.0.0.1:4200"
    echo "  Proxy:         http://127.0.0.1:4100"
    echo "  Install dir:   $INSTALL_DIR"
    echo "  Logs:          $LOG_DIR/"
    echo ""
    echo "  Services are managed by launchd and will auto-start on login + restart on crash."
    echo "    Labels: $PROXY_LABEL, $DASHBOARD_LABEL"
    echo ""
    echo "  To uninstall:"
    echo "    curl -fsSL https://raw.githubusercontent.com/$REPO/main/uninstall.sh | bash"
    echo ""
    echo "  First run on macOS:"
    echo "    The binary is not codesigned for v1 early access. If you see a Gatekeeper prompt on"
    echo "    the first launch, open System Settings → Privacy & Security, scroll down, click"
    echo "    'Allow Anyway' for tokenpulse, then re-run install.sh."
else
    if [ "$NO_AUTOSTART" = "1" ]; then
        echo "  TokenPulse installed to $INSTALL_DIR (auto-start skipped)"
    else
        echo "  TokenPulse installed to $INSTALL_DIR"
    fi
    echo "═══════════════════════════════════════════"
    echo ""
    if [ "$PROXY_OK" = "1" ]; then
        echo "  Start proxy:     $INSTALL_DIR/tokenpulse"
    else
        echo "  Proxy binary not yet available — see messages above to finish setup."
    fi
    if [ -n "$PYTHON3_PATH" ]; then
        echo "  Start dashboard: $PYTHON3_PATH $INSTALL_DIR/web-dashboard.py"
    else
        echo "  Start dashboard: python3 $INSTALL_DIR/web-dashboard.py"
    fi
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
fi
echo "═══════════════════════════════════════════"
