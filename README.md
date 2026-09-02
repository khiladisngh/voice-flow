# Voice Flow

Offline push-to-talk dictation for Linux/Wayland: speak, and clean text lands in the focused window.

[![CI](https://github.com/khiladisngh/voice-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/khiladisngh/voice-flow/actions/workflows/ci.yml)
[![Docs](https://github.com/khiladisngh/voice-flow/actions/workflows/docs.yml/badge.svg)](https://khiladisngh.github.io/voice-flow/)
[![Release](https://img.shields.io/github/v/release/khiladisngh/voice-flow?sort=semver)](https://github.com/khiladisngh/voice-flow/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Wayland-informational.svg)](https://wayland.freedesktop.org/)
[![CUDA](https://img.shields.io/badge/NVIDIA-CUDA%20accelerated-76B900.svg?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![Offline](https://img.shields.io/badge/privacy-100%25%20offline-success.svg)](#privacy)

## Why

Commercial dictation tools ship a multi-process Electron app that idles in the
background, sends your audio to a vendor's servers, and makes you wait on a
network round trip. Voice Flow does the same job entirely on your own machine:
one Python daemon holding the speech model warm in VRAM, a kernel-level hotkey,
and text pasted into the focused window in under half a second. No account, no
subscription, no socket to anyone but localhost.

**It is not a memory optimisation.** Running inference locally costs roughly
what a cloud client costs in RAM, and adds ~3.5 GB of VRAM on top. What you get
for that is privacy, offline operation, and no per-seat fee. See the honest
numbers below.

## Benchmarks

Measured on an NVIDIA RTX 3070 (Fedora, KDE Plasma 6, Python 3.12), median of
5–7 warm runs. Reproduce all of it with
[`scripts/benchmark.py`](scripts/benchmark.py) — stop the daemon first, since it
already holds a Whisper model in VRAM. Your numbers will differ with another
GPU, model size, or compute type.

### Latency

| Stage            | Engine                                  | 1.8 s clip  | 3.4 s clip  | 5.4 s clip  |
| ---------------- | --------------------------------------- | ----------- | ----------- | ----------- |
| Capture          | PipeWire (`pw-record`)                  | <5 ms       | <5 ms       | <5 ms       |
| STT              | `whisper-large-v3-turbo` `int8_float16` | 352 ms      | 430 ms      | 478 ms      |
| Cleanup          | `Qwen3.5-2B Q4_K_M` via Ollama          | 35 ms       | 67 ms       | 74 ms       |
| Injection        | `wl-copy` + `uinput` Ctrl+V             | ~125 ms     | ~125 ms     | ~125 ms     |
| **Text appears** |                                         | **~510 ms** | **~620 ms** | **~680 ms** |

Injection is two numbers, not one. `paste()` delivers Ctrl+V after ~125 ms, then
**sleeps 350 ms before restoring your previous clipboard** — so the daemon is
busy for ~555 ms even though your text landed at ~125 ms. The row above is time
until text is visible, which is what you actually feel. Set
`ui.restore_clipboard` to `false` and the tail disappears at the cost of
Voice Flow keeping the transcript on your clipboard.

### Memory, measured with `/proc/<pid>/smaps_rollup`

PSS is the fair comparison: it charges shared pages once, so a 14-process
Electron app is not penalised for mapping the same libraries repeatedly.

| Process                      | RSS     | PSS     | VRAM     |
| ---------------------------- | ------- | ------- | -------- |
| `voice-flow` daemon          | 1231 MB | 1221 MB | 1228 MiB |
| `ollama` + `llama-server`    | 667 MB  | —       | 2372 MiB |
| A commercial Electron client | 1977 MB | 1014 MB | ~60 MiB  |

So: lower RSS than the Electron client, slightly **higher** PSS.

Voice Flow reserves **~3.5 GiB of VRAM** while running: 1228 MiB for Whisper and
2372 MiB for the Ollama cleaner's `llama-server`, both held resident on purpose
so no utterance pays a model load. Because `cleaner.keep_alive` defaults to `-1`,
the cleanup model never unloads.

That leaves ~4.4 GiB on an otherwise-idle 8 GiB card, minus whatever the rest of
your desktop puts on the GPU — a compositor, browser, and editor together
accounted for another ~690 MiB on the machine these figures come from. Set
`cleaner.keep_alive` to `"5m"` to reclaim ~2.3 GiB when idle, at the cost of a
reload on the first dictation after a pause. The low-VRAM
`Qwen3.5-0.8B Q8_0` alternative uses 1394 MiB.

## Requirements

- **Linux + Wayland** — developed and tested on Fedora with KDE Plasma 6.
- **Python ≥ 3.12**.
- **[uv](https://docs.astral.sh/uv/)** for dependency management.
- **PipeWire** — provides `pw-record` for audio capture.
- **wl-clipboard** — provides `wl-copy` for the paste path.
- **`input` group membership** — required for `evdev` hotkey capture and `uinput` key injection:
  ```bash
  sudo usermod -aG input "$USER"   # log out and back in afterwards
  ```
- **NVIDIA GPU (optional)** — CUDA gives the latencies above; CPU inference works but is noticeably slower.
- **[Ollama](https://ollama.com/) (optional)** — powers transcript cleanup. Without it, set `cleaner.enabled` to `false` and raw transcripts are pasted directly.

## Install

### One line (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/khiladisngh/voice-flow/main/install.sh | sh
```

Clones to `~/.local/share/voice-flow`, installs the Python environment with CUDA
support, pulls the Ollama cleanup model, registers the systemd user service, and
links `voice-flow` into `~/.local/bin`. Re-run it to upgrade. It is idempotent
and never needs root.

Useful switches:

| Variable                | Effect                                   |
| ----------------------- | ---------------------------------------- |
| `VOICE_FLOW_NO_CUDA=1`  | Skip the 2.2 GB NVIDIA wheels (CPU only) |
| `VOICE_FLOW_NO_MODEL=1` | Skip pulling the Ollama cleanup model    |
| `VOICE_FLOW_DIR=...`    | Install somewhere other than the default |
| `VOICE_FLOW_YES=1`      | Non-interactive; assume yes              |

To remove everything:

```bash
~/.local/share/voice-flow/uninstall.sh          # add VOICE_FLOW_PURGE=1 to drop cached models
```

### Homebrew

```bash
brew tap khiladisngh/voice-flow
brew install voice-flow
voice-flow-setup
```

Homebrew installs the CLI only — it does not add you to the `input` group or
start the service, so run `voice-flow-setup` afterwards. The formula is CPU-only;
use the one-line installer if you want CUDA.

### From source

```bash
git clone https://github.com/khiladisngh/voice-flow.git
cd voice-flow

# Install with CUDA acceleration (drop --extra cuda for CPU-only)
uv sync --extra cuda

# Pull the cleanup model
ollama pull hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M

# Install and start the user service. The sed rewrites the unit's paths to
# wherever you cloned, so the repository can live anywhere.
mkdir -p ~/.config/systemd/user
sed "s|^WorkingDirectory=.*|WorkingDirectory=$PWD|; \
     s|^ExecStart=.*|ExecStart=$PWD/voice-flow.sh daemon|" \
  voice-flow.service > ~/.config/systemd/user/voice-flow.service
systemctl --user daemon-reload
systemctl --user enable --now voice-flow
```

The first run downloads the Whisper model (~1.6 GB) into the Hugging Face cache, so the very first dictation takes noticeably longer. Every run after that loads from disk.

Check that the daemon came up:

```bash
systemctl --user status voice-flow
./voice-flow.sh status
```

The `voice-flow` console script lives in `.venv/bin`, so it is only on `PATH`
inside an activated environment. From a clone, `./voice-flow.sh` and
`uv run voice-flow` both work without activation.

## Usage

Hold **`Right Ctrl` + `Right Alt`** and speak — release to transcribe, clean, and paste into the focused window. Tap the same combo instead of holding it to toggle recording on, then tap again to stop. Holding is push-to-talk; tapping is hands-free.

The `voice-flow` command dispatches these subcommands (default is `toggle`):

| Subcommand     | What it does                                                               |
| -------------- | -------------------------------------------------------------------------- |
| `toggle`       | Start recording, or stop and process if a recording is already running.    |
| `status`       | Report whether the daemon is reachable and whether a recording is active.  |
| `daemon`       | Run the resident daemon in the foreground (what the systemd unit invokes). |
| `record-start` | Begin recording without stopping — useful for scripting your own bindings. |
| `record-stop`  | Stop recording, then transcribe, clean, and paste the result.              |

## Configuration

Voice Flow reads `config.json` from the project root. The shipped defaults:

```json
{
  "hotkey": {
    "enabled": true,
    "combo": ["KEY_RIGHTCTRL", "KEY_RIGHTALT"],
    "hold_threshold_sec": 0.45
  },
  "stt": {
    "model_size": "large-v3-turbo",
    "device": "cuda",
    "compute_type": "int8_float16",
    "language": null
  },
  "cleaner": {
    "enabled": true,
    "ollama_url": "http://localhost:11434/api/generate",
    "model": "hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M",
    "temperature": 0.1,
    "timeout_sec": 15.0,
    "keep_alive": -1,
    "options": {}
  },
  "audio": {
    "sample_rate": 16000,
    "channels": 1,
    "temp_file": "auto"
  },
  "ui": {
    "sound_feedback": true,
    "notifications": true,
    "restore_clipboard": true
  }
}
```

| Key                         | Meaning                                                                                                   |
| --------------------------- | --------------------------------------------------------------------------------------------------------- |
| `hotkey.enabled`            | Whether the daemon grabs the global hotkey at all. Disable to drive Voice Flow purely from the CLI.       |
| `hotkey.combo`              | The `evdev` key names that must be held together. Defaults to `Right Ctrl` + `Right Alt`.                 |
| `hotkey.hold_threshold_sec` | Press duration that separates a tap (toggle mode) from a hold (push-to-talk). Defaults to `0.45` seconds. |
| `stt.model_size`            | faster-whisper model to load, e.g. `large-v3-turbo`, `medium`, `small`. Smaller is faster and less exact. |
| `stt.device`                | `cuda` for GPU inference, `cpu` to run without an NVIDIA card.                                            |
| `stt.compute_type`          | CTranslate2 quantisation. `int8_float16` is the measured sweet spot on the RTX 3070; use `int8` on CPU.   |
| `stt.language`              | Force a language code such as `"en"`, or leave `null` to autodetect per utterance.                        |
| `cleaner.enabled`           | Send transcripts through the local LLM for punctuation and filler removal. `false` pastes the raw text.   |
| `cleaner.ollama_url`        | Local Ollama generate endpoint. Change only if Ollama listens elsewhere.                                  |
| `cleaner.model`             | Ollama model used for cleanup. Default `hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M`; any pulled model works.    |
| `cleaner.temperature`       | Sampling temperature for cleanup. Keep it low so the model edits rather than rewrites.                    |
| `cleaner.timeout_sec`       | Client timeout per request. Default `15.0`; slower requests paste the raw transcript instead.             |
| `cleaner.keep_alive`        | How long Ollama holds the model in VRAM. Default `-1` pins it indefinitely.                               |
| `cleaner.options`           | Extra Ollama options for the model, e.g. `{"num_gpu": 999}` on an 8 GB GPU.                               |
| `audio.sample_rate`         | Capture rate in Hz. Whisper expects `16000`; changing it forces a resample.                               |
| `audio.channels`            | Capture channel count. Mono (`1`) is what the models want.                                                |
| `audio.temp_file`           | Where the WAV is written. `auto` resolves to `$XDG_RUNTIME_DIR/voice-flow`.                               |
| `ui.sound_feedback`         | Play a short cue when recording starts and stops.                                                         |
| `ui.notifications`          | Emit desktop notifications for recording and paste events.                                                |
| `ui.restore_clipboard`      | Put your previous clipboard contents back after the paste, so dictation does not clobber what you copied. |

## Architecture

```mermaid
graph LR
    A[Right Ctrl + Right Alt] -->|evdev| B[Hotkey Listener]
    B --> C[PipeWire pw-record]
    C -->|WAV in XDG_RUNTIME_DIR| D[faster-whisper CUDA]
    D -->|raw text| E[Ollama Qwen3.5-2B]
    E -->|clean text| F[wl-copy + uinput Ctrl+V]
    F --> G[Active Wayland Window]
```

The daemon (`voice_flow.daemon`) keeps the Whisper model resident and listens on a Unix socket, so the per-dictation cost is inference only — no model load, no process spawn. The modules are `paths`, `recorder`, `transcriber`, `cleaner`, `injector`, `hotkey`, `daemon`, and `main`.

## Privacy

Voice Flow is 100% offline by construction.

- **Audio never leaves the machine.** Capture writes a local WAV, and transcription runs in-process through faster-whisper. There is no upload path, no telemetry, and no analytics.
- **Transcripts go only to your local Ollama endpoint.** Cleanup posts to `http://localhost:11434` by default. Disable `cleaner.enabled` and even that loopback request disappears.
- **Runtime artefacts are locked down.** The WAV, the socket, and the state files live in `$XDG_RUNTIME_DIR/voice-flow` at mode `0700`, readable only by you, and are cleared when your session ends.

The only network traffic Voice Flow ever generates is the one-time Whisper model download at first run.

## Development

```bash
uv sync --extra cuda --group dev
.venv/bin/pytest
```

The full suite is 51 tests. CI runs the hardware-independent subset:

```bash
.venv/bin/pytest
```

Lint and format with Ruff:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch, commit, and pull request conventions, and the [documentation site](https://khiladisngh.github.io/voice-flow/) for the module reference.

## Acknowledgements

Voice Flow is a thin layer over excellent work by other people:

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — the inference wrapper that makes Whisper practical.
- [CTranslate2](https://github.com/OpenNMT/CTranslate2) — the quantised inference engine underneath it.
- [OpenAI Whisper](https://github.com/openai/whisper) — the speech recognition model.
- [Ollama](https://ollama.com/) and [Qwen](https://github.com/QwenLM/Qwen2.5) — local LLM serving and the cleanup model.
- [python-evdev](https://github.com/gvalkov/python-evdev) — global hotkey capture and `uinput` injection.
- [wl-clipboard](https://github.com/bugaevc/wl-clipboard) — Wayland clipboard access.

## License

Released under the MIT License. See [LICENSE](LICENSE) for the full text.
