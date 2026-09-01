# Task 5: Framed IPC Socket Protocol & Graceful Daemon Lifecycle

## Objective
Implement newline-delimited JSON stream framing on the Unix domain socket (`daemon.sock`) to prevent `JSONDecodeError` on large messages, and add clean signal handlers (`SIGTERM`, `SIGINT`) to guarantee socket cleanup and child process termination on service shutdown.

## Files to touch
- Modify: `voice_flow/daemon.py`
- Modify: `voice_flow/main.py`
- Test: `tests/test_ipc.py`

## Requirements
1. In `voice_flow/main.py`:
   - `send_to_daemon(payload: dict, timeout: float = 15.0) -> dict`:
     - Send `json.dumps(payload).encode("utf-8") + b"\n"`.
     - Read response using `conn.makefile("r", encoding="utf-8").readline()`.
     - Parse JSON. Handle empty response cleanly.
2. In `voice_flow/daemon.py`:
   - Accept loop reads request using `conn.makefile("r", encoding="utf-8").readline()`.
   - Send response with `conn.sendall(json.dumps(result).encode("utf-8") + b"\n")`.
   - In `start_server()`: register signal handlers for `SIGTERM` and `SIGINT` so that `systemctl --user stop voice-flow` unlinks `daemon.sock`, stops `hotkey_listener`, and exits gracefully.
3. Write unit tests in `tests/test_ipc.py`:
   - Test framed communication with mock server/client.
   - Run tests with `/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_ipc.py`.
   - Commit with git.
