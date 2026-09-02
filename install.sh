#!/bin/sh
# Voice Flow installer.
#
#   curl -fsSL https://raw.githubusercontent.com/khiladisngh/voice-flow/main/install.sh | sh
#
# Idempotent: safe to re-run to upgrade an existing install.
#
# Environment overrides:
#   VOICE_FLOW_DIR      install location      (default ~/.local/share/voice-flow)
#   VOICE_FLOW_REF      git ref to install    (default main)
#   VOICE_FLOW_NO_CUDA  set to 1 to skip the 2.2 GB CUDA wheels
#   VOICE_FLOW_NO_MODEL set to 1 to skip pulling the Ollama cleanup model
#   VOICE_FLOW_YES      set to 1 for non-interactive (assume yes)

set -eu

REPO_URL="${VOICE_FLOW_REPO:-https://github.com/khiladisngh/voice-flow.git}"
INSTALL_DIR="${VOICE_FLOW_DIR:-$HOME/.local/share/voice-flow}"
REF="${VOICE_FLOW_REF:-main}"
UNIT_DIR="$HOME/.config/systemd/user"
CLEANUP_MODEL="hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    B=$(printf '\033[1m'); R=$(printf '\033[0m')
    GRN=$(printf '\033[32m'); YLW=$(printf '\033[33m'); RED=$(printf '\033[31m')
else
    B=''; R=''; GRN=''; YLW=''; RED=''
fi

info() { printf '%s==>%s %s\n' "$GRN" "$R" "$1"; }
warn() { printf '%swarning:%s %s\n' "$YLW" "$R" "$1" >&2; }
die()  { printf '%serror:%s %s\n' "$RED" "$R" "$1" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------- preflight ---

[ "$(uname -s)" = "Linux" ] || die "Voice Flow is Linux-only (detected $(uname -s))."

if [ "$(id -u)" = "0" ]; then
    die "Do not run as root. Voice Flow installs into your user account and
       registers a systemd *user* service."
fi

info "Checking prerequisites"

MISSING=''
for cmd in git curl; do
    have "$cmd" || MISSING="$MISSING $cmd"
done
[ -z "$MISSING" ] || die "Missing required commands:$MISSING"

# Runtime dependencies that must come from the distro, not pip.
RUNTIME_MISSING=''
have pw-record || RUNTIME_MISSING="$RUNTIME_MISSING pipewire-utils"
have wl-copy   || RUNTIME_MISSING="$RUNTIME_MISSING wl-clipboard"

if [ -n "$RUNTIME_MISSING" ]; then
    warn "Missing runtime dependencies:$RUNTIME_MISSING"
    if   have dnf;    then printf '  install with: sudo dnf install%s\n' "$RUNTIME_MISSING"
    elif have apt;    then printf '  install with: sudo apt install%s\n' \
                              "$(printf '%s' "$RUNTIME_MISSING" | sed 's/pipewire-utils/pipewire-bin/')"
    elif have pacman; then printf '  install with: sudo pacman -S%s\n' \
                              "$(printf '%s' "$RUNTIME_MISSING" | sed 's/pipewire-utils/pipewire/')"
    elif have zypper; then printf '  install with: sudo zypper install%s\n' "$RUNTIME_MISSING"
    fi
    printf '\nVoice Flow cannot record or paste without these. Continue anyway? [y/N] '
    if [ "${VOICE_FLOW_YES:-}" = "1" ]; then
        printf 'y (VOICE_FLOW_YES=1)\n'
    else
        # Test /dev/tty, not stdin: under `curl … | sh` stdin is the pipe, so
        # `[ -t 0 ]` is false even though the user is sitting at a terminal.
        [ -r /dev/tty ] || die "No terminal available; re-run with VOICE_FLOW_YES=1."
        read -r reply < /dev/tty
        case "$reply" in [yY]*) ;; *) die "Aborted." ;; esac
    fi
fi

if [ "${XDG_SESSION_TYPE:-}" != "wayland" ]; then
    warn "XDG_SESSION_TYPE is '${XDG_SESSION_TYPE:-unset}', not 'wayland'."
    warn "Text injection uses wl-copy and will not work under X11."
fi

# uv provides the Python toolchain; install it if absent.
if ! have uv; then
    info "Installing uv (Python package manager)"
    curl -fsSL https://astral.sh/uv/install.sh | sh
    for candidate in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        # Must be an if, not an AND-list: under `set -e` a failing test as the
        # loop's last command exits the script.
        if [ -x "$candidate/uv" ]; then
            PATH="$candidate:$PATH"
        fi
    done
    export PATH
    have uv || die "uv installed but not on PATH. Open a new shell and re-run."
fi

# ------------------------------------------------------------------ fetch -----

if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing install at $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch --quiet origin "$REF"
    git -C "$INSTALL_DIR" checkout --quiet "$REF"
    git -C "$INSTALL_DIR" reset --quiet --hard "origin/$REF" 2>/dev/null \
        || git -C "$INSTALL_DIR" reset --quiet --hard "$REF"
else
    info "Cloning into $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --quiet --branch "$REF" --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ---------------------------------------------------------------- install -----

if [ "${VOICE_FLOW_NO_CUDA:-}" = "1" ]; then
    info "Installing Python dependencies (CPU only)"
    uv sync --quiet
else
    info "Installing Python dependencies with CUDA support (~2.2 GB)"
    info "Set VOICE_FLOW_NO_CUDA=1 to skip the NVIDIA wheels."
    uv sync --quiet --extra cuda
fi

# ------------------------------------------------------------- input group ----

if ! id -nG | tr ' ' '\n' | grep -qx input; then
    warn "You are not in the 'input' group, so the global hotkey cannot read"
    warn "your keyboard and text injection cannot synthesize Ctrl+V."
    printf '  fix with: sudo usermod -aG input %s   (then log out and back in)\n' "$(id -un)"
    NEEDS_RELOGIN=1
else
    NEEDS_RELOGIN=0
fi

if [ -e /dev/uinput ] && [ ! -w /dev/uinput ]; then
    warn "/dev/uinput exists but is not writable by $(id -un)."
    printf '  fix with:\n'
    printf '    echo '\''KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput", TAG+="uaccess"'\'' | sudo tee /etc/udev/rules.d/99-uinput.rules\n'
    printf '    echo uinput | sudo tee /etc/modules-load.d/uinput.conf\n'
    printf '    sudo udevadm control --reload-rules && sudo udevadm trigger /dev/uinput\n'
fi

# ------------------------------------------------------------- cleanup model --

if [ "${VOICE_FLOW_NO_MODEL:-}" = "1" ]; then
    info "Skipping Ollama model (VOICE_FLOW_NO_MODEL=1)"
elif have ollama; then
    if ollama list 2>/dev/null | awk '{print $1}' | grep -qxF -- "$CLEANUP_MODEL"; then
        info "Ollama cleanup model already present"
    else
        info "Pulling Ollama cleanup model $CLEANUP_MODEL (~2 GB)"
        ollama pull "$CLEANUP_MODEL" || warn "Model pull failed; cleanup will fall back to raw transcripts."
    fi
else
    warn "Ollama not found — transcript cleanup will be disabled."
    warn "Install from https://ollama.com, then: ollama pull $CLEANUP_MODEL"
    warn "Or set cleaner.enabled=false in $INSTALL_DIR/config.json"
fi

# ----------------------------------------------------------------- service ----

# A systemd *user* bus is absent in containers and on SSH sessions without a
# login seat. That is not a reason to fail an otherwise complete install, so
# every systemctl call here is advisory.
HAVE_SYSTEMD=0
if have systemctl && systemctl --user show-environment >/dev/null 2>&1; then
    HAVE_SYSTEMD=1
fi

info "Installing systemd user service"
mkdir -p "$UNIT_DIR"
sed "s|^WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|; \
     s|^ExecStart=.*|ExecStart=$INSTALL_DIR/voice-flow.sh daemon|" \
    voice-flow.service > "$UNIT_DIR/voice-flow.service"
info "Wrote $UNIT_DIR/voice-flow.service"

if [ "$HAVE_SYSTEMD" = "1" ]; then
    systemctl --user daemon-reload || warn "daemon-reload failed; run it yourself."
else
    warn "No systemd user bus detected; skipping service registration."
    warn "Inside a real desktop session, run:"
    warn "  systemctl --user daemon-reload && systemctl --user enable --now voice-flow"
fi

# ------------------------------------------------------------------ launcher --

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/voice-flow.sh" "$BIN_DIR/voice-flow"
info "Linked $BIN_DIR/voice-flow"

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR is not on your PATH; add it to use the 'voice-flow' command." ;;
esac

# -------------------------------------------------------------------- start ---

if [ "$HAVE_SYSTEMD" != "1" ]; then
    : # nothing to start without a user bus
elif [ "$NEEDS_RELOGIN" = "1" ]; then
    warn "Not starting the service yet: add yourself to the 'input' group and"
    warn "log out and back in first, then run: systemctl --user enable --now voice-flow"
else
    info "Enabling and starting the service"
    if systemctl --user enable --now voice-flow; then
        printf 'Waiting for the model to load'
        i=0
        while [ "$i" -lt 60 ]; do
            if "$INSTALL_DIR/voice-flow.sh" status 2>/dev/null | grep -q 'YES'; then
                printf '\n'; info "Daemon is warm"; break
            fi
            printf '.'; sleep 1; i=$((i + 1))
        done
        if [ "$i" -ge 60 ]; then
            printf '\n'
            warn "Daemon did not report ready in 60s."
            warn "Check: journalctl --user -u voice-flow -n 50"
        fi
    else
        warn "Could not start the service. Check: systemctl --user status voice-flow"
    fi
fi

# ------------------------------------------------------------------- done -----

cat <<EOF

${B}Voice Flow is installed.${R}

  Dictate      Hold ${B}Right Ctrl + Right Alt${R}, speak, release.
               Or tap once to start and again to stop.
  Status       voice-flow status
  Logs         journalctl --user -u voice-flow -f
  Config       $INSTALL_DIR/config.json
  Docs         https://khiladisngh.github.io/voice-flow/
  Uninstall    $INSTALL_DIR/uninstall.sh

The first dictation downloads the Whisper model (~1.6 GB) and will be slow.
EOF
