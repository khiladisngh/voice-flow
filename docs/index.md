# Voice Flow

GPU-accelerated, fully offline voice dictation for Linux/Wayland.

Hold **Right Ctrl + Right Alt**, speak, release. The words appear in whatever
window has focus — no cloud, no account, no telemetry.

## Why

Commercial dictation apps ship an Electron shell, a login screen, and a
round-trip to someone else's GPU. Voice Flow does the whole job locally: a
daemon that keeps a Whisper model warm in VRAM and answers in under half a
second. Capture, transcription, cleanup, and injection all happen on your
machine.

!!! warning "This is not a memory optimisation"

    Running inference locally costs about as much host RAM as a cloud client,
    and adds ~2.4 GB of VRAM on top. The wins are privacy, offline operation,
    and no subscription — not footprint.

## Benchmarks

Measured on an NVIDIA RTX 3070 (Fedora, KDE Plasma 6, Wayland, Python 3.12).
Latency is the median of 5 warm runs per utterance.

### Latency, end of speech to pasted text

| Stage          | Engine                                   | 1.8 s clip  | 3.4 s clip  | 5.4 s clip  |
| -------------- | ---------------------------------------- | ----------- | ----------- | ----------- |
| Capture        | PipeWire (`pw-record`)                   | <5 ms       | <5 ms       | <5 ms       |
| Speech-to-text | `whisper-large-v3-turbo`, `int8_float16` | 330 ms      | 360 ms      | 378 ms      |
| Cleanup        | `qwen2.5:1.5b` via Ollama                | 34 ms       | 58 ms       | 57 ms       |
| Injection      | `wl-copy` + `uinput`                     | ~15 ms      | ~15 ms      | ~15 ms      |
| **Total**      |                                          | **~380 ms** | **~435 ms** | **~450 ms** |

### Memory, from `/proc/<pid>/smaps_rollup`

| Process                      | RSS     | PSS     | VRAM     |
| ---------------------------- | ------- | ------- | -------- |
| `voice-flow` daemon          | 1231 MB | 1221 MB | 1146 MiB |
| `ollama` + `llama-server`    | 667 MB  | —       | 1296 MiB |
| A commercial Electron client | 1977 MB | 1014 MB | ~60 MiB  |

PSS charges shared pages once, which is the fair way to compare a 14-process
Electron app against a single daemon. Voice Flow has the lower RSS and the
slightly higher PSS.

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
