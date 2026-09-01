# Task 7 Report: Packaging & Service Reload

## Summary
Corrected Python package configuration by removing the conflicting duplicate stub `src/` directory, updating the entrypoint in `pyproject.toml` to `voice_flow.main:main`, adding `[tool.uv.build-backend]` flat-layout mapping for `uv_build`, modernizing `voice-flow.service` with environment pass-through (`PassEnvironment=WAYLAND_DISPLAY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS`) and `%h` working directory, installing the updated unit file into `~/.config/systemd/user/voice-flow.service`, and reloading the systemd user service.

## Changes Implemented

### 1. `src/` Directory Removal
- Removed `src/` directory containing the outdated stub `src/voice_flow/__init__.py`.
- Ensured all package resolution routes to the canonical `voice_flow/` root package.

### 2. `pyproject.toml`
- Updated script entrypoint:
  ```toml
  [project.scripts]
  voice-flow = "voice_flow.main:main"
  ```
- Configured build backend module root for `uv_build` to support the flat package layout:
  ```toml
  [tool.uv.build-backend]
  module-root = "."
  module-name = "voice_flow"
  ```
- Re-synced environment via `uv sync`, building the wheel and installing the executable entrypoint `voice-flow` into `.venv/bin/voice-flow`.

### 3. `voice-flow.service`
- Updated systemd unit file:
  ```ini
  [Unit]
  Description=Voice Flow Local Dictation Daemon (CUDA + Faster Whisper + Ollama)
  After=network.target sound.target

  [Service]
  Type=simple
  WorkingDirectory=%h/Dev/tools/voice-flow
  ExecStart=%h/Dev/tools/voice-flow/voice-flow.sh daemon
  Restart=on-failure
  RestartSec=3
  PassEnvironment=WAYLAND_DISPLAY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS
  Environment=PYTHONUNBUFFERED=1

  [Install]
  WantedBy=default.target
  ```
- Installed unit to `~/.config/systemd/user/voice-flow.service`.

## Verification

### 1. Packaging & Entrypoint (`uv sync` & CLI)
```bash
$ uv sync
Resolved 36 packages in 0.62ms
   Building voice-flow @ file:///home/gishant-singh/Dev/tools/voice-flow
      Built voice-flow @ file:///home/gishant-singh/Dev/tools/voice-flow
Prepared 1 package in 3ms
Uninstalled 1 package in 0.47ms
Installed 1 package in 1ms
 ~ voice-flow==0.1.0 (from file:///home/gishant-singh/Dev/tools/voice-flow)

$ .venv/bin/voice-flow status
Daemon running: YES (warm in GPU)
Recording active: False
```

### 2. Service Reload & Daemon Restart
```bash
$ systemctl --user daemon-reload && systemctl --user restart voice-flow
```

### 3. Service Status & Journal
```bash
$ systemctl --user status voice-flow
● voice-flow.service - Voice Flow Local Dictation Daemon (CUDA + Faster Whisper + Ollama)
     Loaded: loaded (/home/gishant-singh/.config/systemd/user/voice-flow.service; enabled; preset: disabled)
     Active: active (running) since Wed 2026-09-02 00:25:06 IST; 8s ago
   Main PID: 1109739 (python)
      Tasks: 16 (limit: 38212)
     Memory: 990.4M (peak: 1.7G)
        CPU: 5.945s
     CGroup: /user.slice/user-1000.slice/user@1000.service/app.slice/voice-flow.service
             └─1109739 /home/gishant-singh/Dev/tools/voice-flow/.venv/bin/python -m voice_flow.main daemon
```

Journal verification shows clean initialization and socket creation at the hardened runtime directory:
```
[Daemon] Initializing Transcriber on cuda (large-v3-turbo)...
[Daemon] Connecting to Ollama cleaner (qwen2.5:1.5b)...
[Daemon] Voice Flow Daemon is warm and ready!
[Daemon] Listening on Unix socket: /run/user/1000/voice-flow/daemon.sock
[Hotkey] Listening to keyboard: ROYUAN 2.4G Wireless Keyboard (/dev/input/event7)
[Hotkey] Listening to keyboard: YXT EvoFox Banshee 2 (/dev/input/event4)
[Hotkey] Active global combo: KEY_RIGHTCTRL + KEY_RIGHTALT
```

### 4. End-to-End Status Verification
```bash
$ /home/gishant-singh/Dev/tools/voice-flow/voice-flow.sh status
Daemon running: YES (warm in GPU)
Recording active: False
```

## Status
DONE
