#!/bin/sh
# Voice Flow uninstaller.
#
#   ~/.local/share/voice-flow/uninstall.sh
# or, without a local checkout:
#   curl -fsSL https://raw.githubusercontent.com/khiladisngh/voice-flow/main/uninstall.sh | sh
#
# Environment overrides:
#   VOICE_FLOW_DIR       install location (default ~/.local/share/voice-flow)
#   VOICE_FLOW_YES       set to 1 to skip the confirmation prompt
#   VOICE_FLOW_PURGE     set to 1 to also remove the ~1.6 GB Whisper model cache
#   VOICE_FLOW_KEEP_DIR  set to 1 to keep the checkout (remove the service only)

set -eu

INSTALL_DIR="${VOICE_FLOW_DIR:-$HOME/.local/share/voice-flow}"
UNIT_DIR="$HOME/.config/systemd/user"
BIN_LINK="$HOME/.local/bin/voice-flow"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-flow"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    R=$(printf '\033[0m'); GRN=$(printf '\033[32m')
    YLW=$(printf '\033[33m'); RED=$(printf '\033[31m')
else
    R=''; GRN=''; YLW=''; RED=''
fi

info() { printf '%s==>%s %s\n' "$GRN" "$R" "$1"; }
warn() { printf '%swarning:%s %s\n' "$YLW" "$R" "$1" >&2; }
die()  { printf '%serror:%s %s\n' "$RED" "$R" "$1" >&2; exit 1; }

# Refuse to expand a destructive path to something dangerously short.
safe_rm_rf() {
    target="$1"
    case "$target" in
        ""|"/"|"$HOME"|"$HOME/") die "Refusing to remove '$target'." ;;
    esac
    [ ${#target} -gt 8 ] || die "Refusing to remove suspiciously short path '$target'."
    rm -rf "$target"
}

[ "$(id -u)" != "0" ] || die "Do not run as root; Voice Flow installs per-user."

cat <<EOF
This will remove:
  - the systemd user service      $UNIT_DIR/voice-flow.service
  - the launcher symlink          $BIN_LINK
  - runtime artefacts             $RUNTIME_DIR
EOF
if [ "${VOICE_FLOW_KEEP_DIR:-}" != "1" ]; then
    printf '  - the install directory         %s\n' "$INSTALL_DIR"
fi
if [ "${VOICE_FLOW_PURGE:-}" = "1" ]; then
    printf '  - the Whisper model cache       ~/.cache/huggingface (~1.6 GB)\n'
fi

cat <<EOF

It will NOT remove: uv, Ollama, any Ollama models, or your distro packages
(pipewire, wl-clipboard). Your 'input' group membership is left alone.

EOF

if [ "${VOICE_FLOW_YES:-}" = "1" ]; then
    info "Proceeding (VOICE_FLOW_YES=1)"
elif [ -r /dev/tty ]; then
    # /dev/tty, not stdin: under `curl … | sh` stdin is the pipe, so `[ -t 0 ]`
    # is false even when the user is sitting at a terminal.
    printf 'Continue? [y/N] '
    read -r reply < /dev/tty
    case "$reply" in [yY]*) ;; *) die "Aborted." ;; esac
else
    die "No terminal available; re-run with VOICE_FLOW_YES=1 to confirm."
fi

# ----------------------------------------------------------------- service ----

if systemctl --user list-unit-files voice-flow.service >/dev/null 2>&1; then
    info "Stopping and disabling the service"
    systemctl --user disable --now voice-flow 2>/dev/null || true
fi

if [ -f "$UNIT_DIR/voice-flow.service" ]; then
    rm -f "$UNIT_DIR/voice-flow.service"
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user reset-failed voice-flow 2>/dev/null || true
    info "Removed the unit file"
fi

# A daemon that survived the unit removal (e.g. one started by hand).
if pgrep -f "voice_flow.main daemon" >/dev/null 2>&1; then
    warn "A daemon process is still running; terminating it"
    pkill -TERM -f "voice_flow.main daemon" 2>/dev/null || true
    sleep 1
    pkill -KILL -f "voice_flow.main daemon" 2>/dev/null || true
fi

# --------------------------------------------------------------- artefacts ----

# An if, not `(A || B) && C`: under `set -e` an AND-list whose tests all fail
# returns non-zero and exits the script.
if [ -L "$BIN_LINK" ] || [ -f "$BIN_LINK" ]; then
    rm -f "$BIN_LINK"
    info "Removed $BIN_LINK"
fi

if [ -d "$RUNTIME_DIR" ]; then
    safe_rm_rf "$RUNTIME_DIR"
    info "Removed runtime artefacts (recorded audio, socket, PID file)"
fi

if [ "${VOICE_FLOW_KEEP_DIR:-}" = "1" ]; then
    info "Keeping $INSTALL_DIR (VOICE_FLOW_KEEP_DIR=1)"
elif [ -d "$INSTALL_DIR" ]; then
    # Refuse to delete anything that is not recognisably a Voice Flow checkout.
    if [ -f "$INSTALL_DIR/voice_flow/daemon.py" ] || [ -f "$INSTALL_DIR/voice-flow.sh" ]; then
        safe_rm_rf "$INSTALL_DIR"
        info "Removed $INSTALL_DIR"
    else
        warn "$INSTALL_DIR does not look like a Voice Flow checkout; leaving it alone."
    fi
fi

if [ "${VOICE_FLOW_PURGE:-}" = "1" ]; then
    info "Purging cached Whisper models"
    for d in "$HOME"/.cache/huggingface/hub/models--*faster-whisper* \
             "$HOME"/.cache/huggingface/hub/models--*Systran*; do
        if [ -d "$d" ]; then
            safe_rm_rf "$d"
        fi
    done
fi

# ----------------------------------------------------------------- KDE hint ---

if [ -f "$HOME/.config/kglobalshortcutsrc" ] &&
   grep -q "voice-flow" "$HOME/.config/kglobalshortcutsrc" 2>/dev/null; then
    warn "A KDE global shortcut for Voice Flow remains in kglobalshortcutsrc."
    warn "Remove it under System Settings > Shortcuts if you added one."
fi

printf '\n'
info "Voice Flow removed."
if [ "${VOICE_FLOW_PURGE:-}" != "1" ]; then
    printf '    Whisper models are still cached; re-run with VOICE_FLOW_PURGE=1 to delete them.\n'
fi
