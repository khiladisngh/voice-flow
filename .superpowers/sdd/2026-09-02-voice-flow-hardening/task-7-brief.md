# Task 7: Packaging & Service Reload

## Objective
Correct packaging configuration by removing the conflicting duplicate `src/` stub, pointing `pyproject.toml` script entrypoint directly to `voice_flow.main:main`, updating `voice-flow.service` with environment pass-through, and reloading the active systemd user service.

## Files to touch
- Delete: `src/`
- Modify: `pyproject.toml`
- Modify: `voice-flow.service`
- Verify: `systemctl --user daemon-reload && systemctl --user restart voice-flow`

## Requirements
1. Remove `src/` directory entirely (`rm -rf src`).
2. Update `pyproject.toml`:
   ```toml
   [project.scripts]
   voice-flow = "voice_flow.main:main"
   ```
3. Update `voice-flow.service`:
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
4. Copy `voice-flow.service` to `~/.config/systemd/user/voice-flow.service`.
5. Run `systemctl --user daemon-reload && systemctl --user restart voice-flow`.
6. Verify status with `/home/gishant-singh/Dev/tools/voice-flow/voice-flow.sh status`.
7. Commit changes with git.
