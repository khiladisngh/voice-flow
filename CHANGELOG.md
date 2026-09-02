# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-09-02

### Fixed

- Virtual keyboard injection failure due to `/dev/uinput` permissions: documented and automated the persistent udev rule (`99-uinput.rules`) for modern systemd/Wayland distributions.
- Silent paste failure handling: `TextInjector` now logs explicit errors when `/dev/uinput` cannot be opened or when pasting fails instead of silently swallowing exceptions.
- Accurate paste status reporting: `daemon.py` and `main.py` now track `pasted` boolean status and log `Transcribed & Pasted` or `Transcribed & Paste FAILED` accordingly.

### Added

- Added `/dev/uinput` writability check to `voice-flow status` command and preflight checks in `install.sh`.

## [0.1.1] - 2026-09-02

### Fixed

- `main.py`'s standalone fallback path defaulted `audio.temp_file` to the world-writable `/dev/shm/voice_flow_record.wav` in three places. All three now go through a single `build_recorder()` that honours the `"auto"` sentinel and resolves `$XDG_RUNTIME_DIR/voice-flow` at mode `0700`.
- Ollama evicts an idle model after ~5 minutes, so the first dictation after a pause paid a reload the 4 s cleaner timeout could not absorb — and the fallback to the raw transcript was silent. The cleaner now pins the model with `keep_alive`, warms it at daemon start-up, defaults to a 15 s timeout, and logs every fallback.
- The socket `accept()` loop treated any `OSError` as shutdown, so one transient `ECONNABORTED`/`EINTR` would kill IPC for the daemon's lifetime with no log line. Shutdown is now an explicit flag; transient errors are logged and retried.

### Changed

- Corrected the published benchmarks. The previous figures ("~120 ms transcription, ~200 ms end-to-end, ~85 MB RAM") were not measured against real speech. Measured on an RTX 3070: 330-378 ms transcription, ~380-450 ms end-to-end, and 1231 MB RSS / 1137 MB PSS for the daemon. The README no longer claims a memory saving, because on PSS there isn't one.

### Added

- `scripts/benchmark.py` reproduces every published latency and memory figure from synthesized speech.
- The test suite is now hermetic: it never opens `/dev/uinput`, synthesizes a keystroke, writes the clipboard, or spawns `pw-record`, so CI runs the full suite instead of a subset. Previously running `pytest` pasted into the developer's focused window and overwrote their clipboard.

## [0.1.0] - 2026-09-02

### Added

- Offline dictation daemon: `faster-whisper` `large-v3-turbo` on CUDA (`int8_float16`) with a warm model held in VRAM.
- Local LLM post-processing via Ollama (`qwen2.5:1.5b`) that strips fillers and restores punctuation.
- Kernel-level global hotkey (`Right Ctrl + Right Alt`) over `evdev`, supporting both push-to-talk and tap-to-toggle.
- Wayland text injection through `wl-copy` plus a persistent `uinput` virtual keyboard, with clipboard restore.
- Unix-socket IPC with newline-delimited JSON framing, and a `systemd` user service.
- Documentation site, VS Code workspace tasks, and a 51-test suite.

### Security

- Runtime artefacts (audio, PID, socket) live in `$XDG_RUNTIME_DIR/voice-flow` at mode `0700` instead of world-writable `/dev/shm`.
- Dictated speech is wrapped in `<spoken_text>` delimiters before reaching the LLM to contain prompt injection.

[Unreleased]: https://github.com/khiladisngh/voice-flow/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/khiladisngh/voice-flow/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/khiladisngh/voice-flow/releases/tag/v0.1.0
