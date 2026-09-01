# Voice Flow

High-performance, Wayland-native voice dictation engineered for NVIDIA GPUs (RTX 3070). Direct, open-source replacement for Wispr Flow with **~95% less RAM usage** and sub-250ms latency.

---

## Global Hotkey: `Right Ctrl + Right Alt`

Voice Flow listens directly to kernel input (`evdev`) across your physical keyboards without relying on Wayland compositor shortcut quirks:

1. **Push-to-Talk (Hold):** Press and hold **`Right Ctrl + Right Alt`**, speak, and release to paste.
2. **Toggle Mode (Tap):** Quick-tap **`Right Ctrl + Right Alt`** to start listening hands-free, then tap again to finish and paste.

You will hear a chime and see a `🎙️ Listening...` notification whenever recording is active.

---

## Architecture & Benchmark

| Component | Engine | Hardware | Latency | VRAM / RAM |
| :--- | :--- | :--- | :--- | :--- |
| **Speech-to-Text (STT)** | `whisper-large-v3-turbo` (`faster-whisper`) | CUDA (`int8_float16`) | ~120ms | ~1.1 GB VRAM |
| **LLM Post-Processing** | `qwen2.5:1.5b` (Ollama) | CUDA | ~66ms | ~1.2 GB VRAM |
| **Audio Capture** | PipeWire (`pw-record`) | RAM (`/dev/shm`) | <5ms | 0 MB |
| **Input Injection** | `wl-copy` + `evdev` uinput `Ctrl+V` | Wayland native | ~10ms | 0 MB |
| **Total Pipeline** | **End-to-end Voice to Screen** | **100% Local / Offline** | **~200ms** | **~85 MB RAM** |

---

## Managing the Service

Voice Flow runs as a systemd user service in the background:

```bash
# Check status
systemctl --user status voice-flow

# View real-time logs
journalctl --user -u voice-flow -f

# Restart daemon
systemctl --user restart voice-flow
```

---

## Customizing Hotkeys (`config.json`)

To change the keys or threshold:

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
    "compute_type": "int8_float16"
  },
  "cleaner": {
    "enabled": true,
    "model": "qwen2.5:1.5b"
  }
}
```
