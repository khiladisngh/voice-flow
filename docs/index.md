# Voice Flow

GPU-accelerated, fully offline voice dictation for Linux/Wayland.

Hold **Right Ctrl + Right Alt**, speak, release. The words appear in whatever
window has focus — no cloud, no account, no telemetry.

## Why

Commercial dictation apps ship an Electron shell, a login screen, and a
round-trip to someone else's GPU. Voice Flow replaces roughly 2 GB of that with
an ~85 MB resident daemon that keeps a Whisper model warm in VRAM and answers in
about 200 ms end-to-end. Everything — capture, transcription, cleanup, and
injection — happens on your machine.

## Benchmarks

Measured on an NVIDIA RTX 3070 (Fedora, KDE Plasma 6, Wayland).

| Component      | Engine                                   | Latency     | Footprint      |
| -------------- | ---------------------------------------- | ----------- | -------------- |
| Capture        | PipeWire (`pw-record`)                   | <5 ms       | 0 MB           |
| Speech-to-text | `whisper-large-v3-turbo`, `int8_float16` | ~120 ms     | ~1.1 GB VRAM   |
| Cleanup        | `qwen2.5:1.5b` via Ollama                | 66 ms       | ~1.2 GB VRAM   |
| Injection      | `wl-copy` + `uinput`                     | ~15 ms      | 0 MB           |
| **Total**      |                                          | **~200 ms** | **~85 MB RAM** |

The RAM figure is the resident daemon process; the VRAM figures are models held
warm so that no load cost is paid per utterance.

## Features

- **Fully offline.** Audio never leaves the machine. Transcripts go only to a
  local Ollama endpoint you configure, and cleanup can be switched off entirely.
- **Warm daemon.** The Whisper model is loaded once at start-up and stays in
  VRAM, so dictation latency is inference time, not model-load time.
- **Kernel-level hotkey.** The listener reads `/dev/input` through `evdev`, so
  the shortcut works in every application, including ones that swallow
  compositor shortcuts.
- **Push-to-talk _and_ toggle.** Hold the combo to dictate while held; tap it to
  start, tap again to stop. One shortcut, both behaviours.
- **Wayland text injection.** Text is placed on the clipboard with `wl-copy` and
  pasted with a synthetic `Ctrl+V` from a persistent `uinput` virtual keyboard.
  The previous clipboard contents are restored afterwards.
- **LLM post-processing.** A local 1.5B model strips "um", "uh", and "you know",
  restores punctuation and capitalisation, and formats numbers and units.
- **Secure by construction.** Recorded audio, the PID file, and the IPC socket
  live in `$XDG_RUNTIME_DIR/voice-flow` at mode `0700`.
- **Graceful degradation.** No GPU? Run Whisper on the CPU. No Ollama? Cleanup
  falls back to raw transcript text without failing the dictation.

## Requirements at a glance

- Linux with a Wayland session (developed on Fedora + KDE Plasma 6)
- Python 3.12 or newer, and [uv](https://docs.astral.sh/uv/)
- PipeWire (`pw-record`) and `wl-clipboard`
- Membership of the `input` group
- Optional: an NVIDIA GPU for CUDA acceleration
- Optional: [Ollama](https://ollama.com/) for transcript cleanup

## Next steps

- [Installation](installation.md) — system packages, `input` group, systemd unit,
  and the CPU-only fallback.
- [Usage](usage.md) — hotkey behaviour, every CLI subcommand, and binding your
  own shortcut.
- [Configuration](configuration.md) — every `config.json` key with its type,
  default, and effect.
- [Architecture](architecture.md) — the pipeline, module responsibilities, the
  IPC contract, and the security decisions.
- [Troubleshooting](troubleshooting.md) — symptom, cause, fix.
- [Development](development.md) — repo layout, testing contract, lint, release.

## License

MIT. See [`LICENSE`](https://github.com/khiladisngh/voice-flow/blob/main/LICENSE).
