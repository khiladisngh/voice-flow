# Task 1: Secure Runtime Directory Isolation

## Objective
Relocate all temporary audio, socket, and PID files from world-writable `/dev/shm` (mode 1777) to `$XDG_RUNTIME_DIR/voice-flow` (mode 0700).

## Files to touch
- Create: `voice_flow/paths.py`
- Modify: `voice_flow/recorder.py`
- Modify: `voice_flow/daemon.py`
- Modify: `config.json`
- Test: `tests/test_paths.py`

## Requirements
1. Implement `voice_flow/paths.py`:
   - `get_runtime_dir() -> Path`: Resolves `$XDG_RUNTIME_DIR` (or fallback `/run/user/<uid>`) / "voice-flow". Creates with `mode=0o700`.
   - `get_audio_path(session_id: str = "current") -> Path`: Returns `get_runtime_dir() / f"record_{session_id}.wav"`.
   - `get_pid_file() -> Path`: Returns `get_runtime_dir() / "recorder.pid"`.
   - `get_socket_path() -> Path`: Returns `get_runtime_dir() / "daemon.sock"`.
2. Update `recorder.py`:
   - Use `get_pid_file()` and `get_audio_path()` from `voice_flow.paths`.
   - Remove any hardcoded `/dev/shm` paths.
3. Update `daemon.py`:
   - Use `get_socket_path()` and `get_runtime_dir()` from `voice_flow.paths`.
   - Remove hardcoded `Path.home() / ".cache" / "voice-flow"`.
4. Update `config.json`:
   - Change `audio.temp_file` to `"auto"` or remove `/dev/shm` default.
5. Create `tests/test_paths.py`:
   - Verify permissions are `0700` and paths are correct when `XDG_RUNTIME_DIR` is set.
   - Run tests with `/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_paths.py`.
   - Commit with git.
