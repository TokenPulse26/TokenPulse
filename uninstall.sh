#!/usr/bin/env bash
set -euo pipefail

# TokenPulse Uninstaller
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/uninstall.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/uninstall.sh | bash -s -- --keep-data
#   curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/uninstall.sh | bash -s -- --yes
#
# Flags:
#   --yes, -y     Skip the "delete your database?" confirmation.
#   --keep-data   Move tokenpulse.db to $HOME/tokenpulse-backup-<timestamp>.db before removing the install dir.
#   --help, -h    Print usage.

YES=0
KEEP_DATA=0

print_usage() {
    cat <<'EOF'
TokenPulse Uninstaller

Removes the TokenPulse launchd services, plist files, and install directory.

Usage:
  uninstall.sh [--yes] [--keep-data] [--help]

Flags:
  --yes, -y      Skip the "delete your SQLite database?" confirmation.
  --keep-data    Move tokenpulse.db to $HOME/tokenpulse-backup-<timestamp>.db
                 before removing the install directory.
  --help, -h     Print this help and exit.

What gets removed:
  - launchd services: com.tokenpulse.proxy, com.tokenpulse.dashboard
  - $HOME/Library/LaunchAgents/com.tokenpulse.proxy.plist
  - $HOME/Library/LaunchAgents/com.tokenpulse.dashboard.plist
  - $HOME/.tokenpulse/ (the entire install directory, including logs)

What is NEVER touched:
  - Anything outside $HOME/.tokenpulse/ and $HOME/Library/LaunchAgents/com.tokenpulse.*.plist
    (plus the explicit backup file, if --keep-data was passed)
EOF
}

for arg in "$@"; do
    case "$arg" in
        --yes|-y)
            YES=1
            ;;
        --keep-data)
            KEEP_DATA=1
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown flag: $arg"
            echo ""
            print_usage
            exit 1
            ;;
    esac
done

# --- Safety: make sure HOME is set to something sane before we touch paths derived from it.
if [ -z "${HOME:-}" ] || [ "$HOME" = "/" ]; then
    echo "❌ HOME is not set to a safe value. Refusing to run."
    exit 1
fi

INSTALL_DIR="$HOME/.tokenpulse"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PROXY_LABEL="com.tokenpulse.proxy"
DASHBOARD_LABEL="com.tokenpulse.dashboard"
PROXY_PLIST="$LAUNCH_AGENTS_DIR/$PROXY_LABEL.plist"
DASHBOARD_PLIST="$LAUNCH_AGENTS_DIR/$DASHBOARD_LABEL.plist"

# Guard: INSTALL_DIR must be exactly $HOME/.tokenpulse and non-empty.
if [ "$INSTALL_DIR" != "$HOME/.tokenpulse" ] || [ -z "$INSTALL_DIR" ]; then
    echo "❌ Computed INSTALL_DIR ($INSTALL_DIR) doesn't look right. Aborting."
    exit 1
fi

echo "TokenPulse uninstaller"
echo "  Install dir: $INSTALL_DIR"
echo "  Plists:      $PROXY_PLIST"
echo "               $DASHBOARD_PLIST"
echo ""

REMOVED_ITEMS=()

# --- Step 1: unload launchd services (best effort, never fatal)
unload_service() {
    local label="$1"
    local plist="$2"
    local unloaded=0
    if launchctl list 2>/dev/null | awk '{print $3}' | grep -Fxq "$label"; then
        if launchctl bootout "gui/$(id -u)/$label" 2>/dev/null; then
            unloaded=1
        elif launchctl unload "$plist" 2>/dev/null; then
            unloaded=1
        fi
    elif [ -f "$plist" ]; then
        # Not listed but file exists — try unload anyway.
        launchctl unload "$plist" 2>/dev/null || true
        unloaded=1
    fi
    if [ "$unloaded" = "1" ]; then
        echo "  Unloaded launchd service: $label"
        REMOVED_ITEMS+=("launchd service: $label")
    fi
}

echo "Stopping services..."
unload_service "$PROXY_LABEL" "$PROXY_PLIST"
unload_service "$DASHBOARD_LABEL" "$DASHBOARD_PLIST"

# --- Step 2: remove plist files
remove_plist() {
    local plist="$1"
    if [ -f "$plist" ]; then
        rm -f "$plist"
        echo "  Removed plist: $plist"
        REMOVED_ITEMS+=("$plist")
    fi
}

remove_plist "$PROXY_PLIST"
remove_plist "$DASHBOARD_PLIST"

# --- Step 3: handle the install directory
if [ ! -d "$INSTALL_DIR" ]; then
    echo ""
    echo "No install directory at $INSTALL_DIR — nothing to remove there."
    echo ""
    if [ "${#REMOVED_ITEMS[@]}" -eq 0 ]; then
        echo "Nothing was removed. TokenPulse doesn't appear to be installed for this user."
    else
        echo "TokenPulse partially removed:"
        for item in "${REMOVED_ITEMS[@]}"; do
            echo "  - $item"
        done
    fi
    exit 0
fi

# Guard on the rm path one more time.
case "$INSTALL_DIR" in
    "$HOME/.tokenpulse")
        ;;
    *)
        echo "❌ Refusing to remove an install dir that isn't \$HOME/.tokenpulse ($INSTALL_DIR)."
        exit 1
        ;;
esac

DB_PATH="$INSTALL_DIR/tokenpulse.db"

# Optional: back up the DB before we touch anything destructive.
if [ "$KEEP_DATA" = "1" ]; then
    if [ -f "$DB_PATH" ]; then
        ts=$(date +%Y%m%d-%H%M%S)
        backup="$HOME/tokenpulse-backup-$ts.db"
        cp "$DB_PATH" "$backup"
        echo "  Backed up SQLite DB: $backup"
        REMOVED_ITEMS+=("backup created: $backup")
    else
        echo "  --keep-data was set, but no $DB_PATH was found. Nothing to back up."
    fi
fi

# Confirm before blowing away the DB unless --yes or --keep-data was passed.
if [ "$YES" = "0" ] && [ "$KEEP_DATA" = "0" ] && [ -f "$DB_PATH" ]; then
    if [ -t 0 ]; then
        echo ""
        echo "This will permanently delete your TokenPulse request history at:"
        echo "    $DB_PATH"
        echo ""
        printf "Delete TokenPulse data? [y/N] "
        read -r reply
        case "$reply" in
            y|Y|yes|YES) ;;
            *)
                echo "Cancelled. Nothing further was removed."
                echo ""
                if [ "${#REMOVED_ITEMS[@]}" -gt 0 ]; then
                    echo "Partial cleanup already performed:"
                    for item in "${REMOVED_ITEMS[@]}"; do
                        echo "  - $item"
                    done
                    echo ""
                    echo "Re-run with --keep-data to preserve the DB, or --yes to confirm deletion."
                fi
                exit 0
                ;;
        esac
    else
        echo ""
        echo "Non-interactive shell detected and no --yes / --keep-data flag was passed."
        echo "Refusing to silently delete $DB_PATH."
        echo ""
        echo "Re-run with one of:"
        echo "  curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/uninstall.sh | bash -s -- --yes"
        echo "  curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/uninstall.sh | bash -s -- --keep-data"
        exit 1
    fi
fi

# Now nuke the install dir.
rm -rf -- "$INSTALL_DIR"
echo "  Removed install dir: $INSTALL_DIR"
REMOVED_ITEMS+=("$INSTALL_DIR (and all contents, including logs)")

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ TokenPulse fully removed"
echo "═══════════════════════════════════════════"
echo ""
echo "Removed:"
for item in "${REMOVED_ITEMS[@]}"; do
    echo "  - $item"
done
echo ""
if [ "$KEEP_DATA" = "1" ] && [ -f "$backup" ] 2>/dev/null; then
    echo "Your request history was preserved at:"
    echo "  $backup"
    echo ""
fi
echo "Reinstall anytime with:"
echo "  curl -fsSL https://raw.githubusercontent.com/TokenPulse26/TokenPulse/main/install.sh | bash"
