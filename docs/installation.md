# Installation

Voice Flow is a Linux/Wayland application. It needs PipeWire for capture,
`wl-clipboard` for the Wayland clipboard, and read access to `/dev/input` plus
write access to `/dev/uinput` for the hotkey and paste keystroke.

## 1. System packages

Fedora:

```bash
sudo dnf install pipewire-utils wl-clipboard
```

Debian / Ubuntu:

```bash
sudo apt install pipewire-bin wl-clipboard
```

`pipewire-utils` / `pipewire-bin` provide `pw-record` (capture) and `pw-play`
(the optional start/stop sounds). `wl-clipboard` provides `wl-copy` and
`wl-paste`.

Verify both are on `PATH`:

```bash
command -v pw-record wl-copy wl-paste
```

## 2. Join the `input` group and ensure `/dev/uinput` is writable

The daemon reads keyboard events from `/dev/input/event*` and writes synthetic
keystrokes to `/dev/uinput`. On many distributions `/dev/input/event*` is owned by
the `input` group, while `/dev/uinput` requires a udev rule to allow `input` group write access.

Add yourself to the `input` group:

```bash
sudo usermod -aG input $USER
```

Ensure `/dev/uinput` is automatically granted `input` group write permissions:

```bash
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/99-uinput.rules
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
sudo udevadm control --reload-rules && sudo udevadm trigger /dev/uinput
```

!!! warning "A re-login is required"
Group membership is only applied to new login sessions. Log out and back in
(or reboot) before continuing — `newgrp` is not enough, because the systemd
user manager that will run the daemon inherits its groups from the session.

Confirm afterwards:

```bash
id -nG | tr ' ' '\n' | grep -x input
test -w /dev/uinput && echo "uinput writable"
```

Both must succeed before running the daemon.

## 3. Install `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

See the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/)
for package-manager alternatives.

## 4. Clone and sync

```bash
git clone https://github.com/khiladisngh/voice-flow.git
cd voice-flow
uv sync --extra cuda
```

The `cuda` extra pulls `nvidia-cublas-cu12` and `nvidia-cudnn-cu12`. They are
about 2.2 GB installed, which is why they are an optional extra rather than a
hard dependency — see [CPU-only fallback](#cpu-only-fallback) if you do not have
an NVIDIA GPU.

For a development environment, add the dev dependency group:

```bash
uv sync --extra cuda --group dev
```

Check that CTranslate2 can see the GPU:

```bash
.venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

Expected: `1` (or higher). `0` means the CUDA runtime is not visible; see
[Troubleshooting](troubleshooting.md).

!!! note "First run downloads the model"
The Whisper `large-v3-turbo` weights (~1.6 GB) are fetched into the Hugging
Face cache (`~/.cache/huggingface`) the first time the daemon starts. That
single download needs network access; nothing afterwards does.

## 5. Pull the cleanup model

Transcript cleanup runs against a local [Ollama](https://ollama.com/) server.

```bash
ollama pull hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M
```

Verify the endpoint the daemon will use:

```bash
curl -s http://localhost:11434/api/tags | head -c 200
```

If you would rather not run Ollama, set `cleaner.enabled` to `false` in
`config.json`. Dictation then pastes the raw Whisper transcript.

## 6. Install the systemd user service

The repository ships `voice-flow.service`. Its `WorkingDirectory` and
`ExecStart` default to `%h/voice-flow`, so rather than editing the unit by
hand, install it through `sed` and let it point at your actual checkout:

```bash
mkdir -p ~/.config/systemd/user
sed "s|^WorkingDirectory=.*|WorkingDirectory=$PWD|; \
     s|^ExecStart=.*|ExecStart=$PWD/voice-flow.sh daemon|" \
  voice-flow.service > ~/.config/systemd/user/voice-flow.service
systemctl --user daemon-reload
systemctl --user enable --now voice-flow
```

!!! note "Why `sed` instead of `cp`"

    Run the command from inside the clone, so `$PWD` is the repository root.
    This keeps the unit correct whether you cloned to `~/voice-flow`,
    `~/src/voice-flow`, or anywhere else. Everything else in the unit already
    uses `%h`, never an absolute home path.

Confirm the daemon is warm:

```bash
./voice-flow.sh status
```

Expected:

```
Daemon running: YES (warm in GPU)
Recording active: False
```

Follow the start-up log if it is not:

```bash
journalctl --user -u voice-flow -f
```

A healthy start-up prints the model being loaded, one
`[Hotkey] Listening to keyboard: ...` line per detected keyboard, the active
combo, and finally `[Daemon] Voice Flow Daemon is warm and ready!`.

## CPU-only fallback

Voice Flow runs without an NVIDIA GPU. Sync without the `cuda` extra and point
the transcriber at the CPU:

```bash
uv sync
```

Then edit `config.json`:

```json
{
  "stt": {
    "model_size": "large-v3-turbo",
    "device": "cpu",
    "compute_type": "int8",
    "language": null
  }
}
```

`int8` is the correct compute type for CPU inference; `int8_float16` requires
CUDA. Expect transcription to take seconds rather than ~360 ms. Dropping
`stt.model_size` to `small` or `base` trades accuracy for a large speed gain —
see [Configuration](configuration.md#stt) for the model trade-off table.

Cleanup also runs on the CPU: `hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M` is small
enough that Ollama can serve it without a GPU, just more slowly. If the round
trip exceeds the 15-second client timeout, the raw transcript is pasted instead.

## Uninstall

```bash
systemctl --user disable --now voice-flow
rm ~/.config/systemd/user/voice-flow.service
systemctl --user daemon-reload
rm -rf ~/.cache/huggingface/hub/models--*faster-whisper*
```

Then delete the checkout. Runtime artefacts under
`$XDG_RUNTIME_DIR/voice-flow` are tmpfs-backed and disappear at logout.

Next: [Usage](usage.md).
