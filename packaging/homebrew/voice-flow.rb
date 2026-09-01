# Homebrew formula for Voice Flow.
#
# This copy is the source of truth. It is published to the tap repository
# khiladisngh/homebrew-voice-flow as Formula/voice-flow.rb.
#
#   brew tap khiladisngh/voice-flow
#   brew install voice-flow
#   voice-flow-setup
#
# Homebrew installs the CLI and its Python dependencies. It deliberately does
# NOT register the systemd user service or add you to the `input` group —
# neither belongs in a package manager. `voice-flow-setup` does that, and
# reports whatever is still missing.
class VoiceFlow < Formula
  include Language::Python::Virtualenv

  desc "Offline GPU-accelerated voice dictation for Linux/Wayland"
  homepage "https://khiladisngh.github.io/voice-flow/"
  url "https://github.com/khiladisngh/voice-flow/archive/refs/tags/v0.1.1.tar.gz"
  sha256 "PLACEHOLDER_REPLACED_BY_make_brew_sync"
  license "MIT"
  head "https://github.com/khiladisngh/voice-flow.git", branch: "main"

  # Wayland injection, evdev hotkeys, PipeWire capture, and systemd user
  # services are Linux-only. There is no macOS implementation.
  depends_on :linux
  depends_on "python@3.12"

  def install
    # NOTE: deliberately not `virtualenv_install_with_resources`.
    #
    # That helper installs with --no-deps and requires one `resource` stanza per
    # transitive dependency. This project pulls 58 distributions, including
    # ctranslate2, onnxruntime, and av — several of which would have to be
    # compiled from source. Maintaining that by hand is neither reliable nor
    # reviewable, so the virtualenv resolves dependencies from PyPI instead.
    # A custom tap is the right place for that trade-off; homebrew-core is not.
    virtualenv_create(libexec, "python3.12")
    system libexec/"bin/python", "-m", "pip", "install", "--no-cache-dir", buildpath
    bin.install_symlink libexec/"bin/voice-flow"

    # voice-flow-setup needs the unit template and the default config.
    pkgshare.install "voice-flow.service", "config.json"

    (bin/"voice-flow-setup").write <<~EOS
      #!/bin/sh
      # Finish a Homebrew install: register the systemd user service and report
      # anything still missing.
      set -eu

      UNIT_DIR="$HOME/.config/systemd/user"
      CONFIG_DIR="$HOME/.config/voice-flow"

      if [ "$(uname -s)" != "Linux" ]; then
        echo "Voice Flow is Linux-only." >&2
        exit 1
      fi

      mkdir -p "$UNIT_DIR" "$CONFIG_DIR"

      if [ ! -f "$CONFIG_DIR/config.json" ]; then
        cp "#{pkgshare}/config.json" "$CONFIG_DIR/config.json"
        echo "==> Wrote default config to $CONFIG_DIR/config.json"
      fi

      sed "s|^WorkingDirectory=.*|WorkingDirectory=#{pkgshare}|; \\
           s|^ExecStart=.*|ExecStart=#{bin}/voice-flow daemon|" \\
        "#{pkgshare}/voice-flow.service" > "$UNIT_DIR/voice-flow.service"
      echo "==> Wrote $UNIT_DIR/voice-flow.service"

      for cmd in pw-record wl-copy; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
          echo "warning: $cmd not found; install pipewire-utils and wl-clipboard" >&2
        fi
      done

      if ! id -nG | tr ' ' '\\n' | grep -qx input; then
        echo "warning: not in the 'input' group; the global hotkey cannot read your keyboard" >&2
        echo "  sudo usermod -aG input $(id -un)   # then log out and back in" >&2
      fi

      if ! command -v ollama >/dev/null 2>&1; then
        echo "warning: ollama not found; transcript cleanup will be skipped" >&2
      fi

      if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
        systemctl --user daemon-reload
        echo "==> Now run: systemctl --user enable --now voice-flow"
      else
        echo "warning: no systemd user bus; register the service from a desktop session" >&2
      fi
    EOS
    chmod 0755, bin/"voice-flow-setup"
  end

  def caveats
    <<~EOS
      Homebrew installed the CLI only. Finish setup with:

        voice-flow-setup
        sudo usermod -aG input $(id -un)   # then log out and back in
        systemctl --user enable --now voice-flow

      Runtime dependencies come from your distribution, not Homebrew:
        Fedora:  sudo dnf install pipewire-utils wl-clipboard
        Debian:  sudo apt install pipewire-bin wl-clipboard

      Transcript cleanup needs Ollama (https://ollama.com):
        ollama pull qwen2.5:1.5b

      This formula installs CPU-only dependencies. For NVIDIA acceleration use
      the standalone installer, which handles the CUDA wheels:
        curl -fsSL https://raw.githubusercontent.com/khiladisngh/voice-flow/main/install.sh | sh
    EOS
  end

  test do
    # Must run without a daemon, a GPU, or a Wayland session, which is all the
    # brew test sandbox provides.
    assert_match "Usage: voice-flow", shell_output("#{bin}/voice-flow not-a-subcommand 2>&1")
    assert_match "Daemon running", shell_output("#{bin}/voice-flow status 2>&1")
    assert_predicate bin/"voice-flow-setup", :executable?
  end
end
