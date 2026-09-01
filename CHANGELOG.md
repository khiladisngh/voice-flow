# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/khiladisngh/voice-flow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/khiladisngh/voice-flow/releases/tag/v0.1.0
