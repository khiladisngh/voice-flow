# Task 5 Report: Framed IPC Socket Protocol & Graceful Daemon Lifecycle

## 1. Overview
Task 5 addresses IPC communication reliability and graceful service shutdown in `voice-flow`:
1. **Unframed Socket Buffering & Message Truncation:** Previously, `send_to_daemon()` in `voice_flow/main.py` and the accept loop in `voice_flow/daemon.py` performed raw `recv(8192)` / `recv(4096)` calls without message stream framing. Large payloads (such as extended transcription responses or debug dumps) exceeding the single recv buffer resulted in truncated byte streams, leading to `json.JSONDecodeError`.
2. **Hardcoded Legacy Socket Path:** `main.py` used a hardcoded legacy path (`~/.cache/voice-flow/daemon.sock`) rather than dynamically resolving `$XDG_RUNTIME_DIR/voice-flow/daemon.sock` via `voice_flow.paths.get_socket_path()`, breaking runtime isolation and causing client commands to connect to stale or nonexistent sockets.
3. **Missing Signal Handlers & Dirty Shutdown:** `VoiceFlowDaemon.start_server()` lacked signal handlers for `SIGTERM` and `SIGINT`. When stopped via `systemctl --user stop voice-flow` or manual interruption, the Python process was terminated abruptly without executing socket unlinking, leaving stale `daemon.sock` files in the runtime directory and orphan hotkey listener background workers.

Both `main.py` and `daemon.py` now implement newline-delimited JSON (`\n`) stream framing via `conn.makefile("r", encoding="utf-8").readline()`. Additionally, `VoiceFlowDaemon` registers signal handlers for `SIGTERM` and `SIGINT` to guarantee graceful resource teardown (`hotkey_listener.stop()`, unlinking `daemon.sock`, and closing the server socket).

## 2. Implementation Summary

### Modified Files
- `voice_flow/main.py`:
  - Imported `get_socket_path` from `voice_flow.paths`.
  - Replaced hardcoded legacy cache socket path with dynamic `get_socket_path()`.
  - Updated `send_to_daemon(payload: dict, timeout: float = 15.0) -> dict`:
    - Checks `sock_path.exists()` before connecting.
    - Encodes and frames payload with trailing newline: `json.dumps(payload).encode("utf-8") + b"\n"`.
    - Reads responses using `with client.makefile("r", encoding="utf-8") as f: line = f.readline()`.
    - Handles empty responses by raising `ConnectionResetError("Empty response from daemon")`.
    - Parses and returns `json.loads(line)`.
  - Updated status check in `main()` to query `get_socket_path().exists()`.

- `voice_flow/daemon.py`:
  - Added `import signal`.
  - Implemented `_handle_signal(self, signum, frame)`:
    - Logs signal receipt and executes `self.stop()`.
    - Exits with `sys.exit(0)`.
  - Implemented `register_signal_handlers(self)`:
    - Registers `_handle_signal` for `signal.SIGTERM` and `signal.SIGINT`.
    - Catches `(ValueError, AttributeError)` so daemon execution within worker threads or non-standard environments does not throw unhandled exceptions.
  - Implemented `stop(self)`:
    - Stops `self.hotkey_listener` if active.
    - Unlinks `daemon.sock` from the filesystem if present.
    - Closes `self.server` socket if active.
  - Hardened `start_server(self)`:
    - Removes existing stale socket file prior to binding.
    - Registers signal handlers upon startup.
    - In accept loop:
      - Reads request using `conn.makefile("r", encoding="utf-8").readline()`.
      - Skips empty connections.
      - Dispatches actions: `ping`, `process`, `toggle`, or error reporting.
      - Sends newline-framed JSON response: `conn.sendall(json.dumps(res).encode("utf-8") + b"\n")`.
      - Catches exceptions and returns JSON-encoded error response with newline.
      - Closes client connection in `finally: conn.close()`.
    - In `finally:` block: invokes `self.stop()` and restores previous signal handlers if any were displaced.

### Created Files
- `tests/test_ipc.py`:
  - `test_framed_socket_communication`: Verifies newline-delimited framing across mock server and `send_to_daemon` client.
  - `test_send_to_daemon_empty_response_handling`: Verifies clean error handling (`ConnectionResetError`) when daemon closes connection without sending data.
  - `test_send_to_daemon_large_payload`: Verifies large payloads (32KB+) transmit and decode completely without buffer truncation.
  - `test_send_to_daemon_missing_socket`: Verifies `ConnectionError` is raised with a descriptive message when the socket file is missing.
  - `test_daemon_framed_server_loop`: Verifies `VoiceFlowDaemon.start_server()` accept loop handles `ping`, `toggle` (start/stop), `process`, and invalid actions over newline-framed IPC.
  - `test_daemon_signal_handling_and_lifecycle`: Verifies `SIGTERM` and `SIGINT` signal registration, handler invocation, socket unlinking, and hotkey listener shutdown.

## 3. TDD Process & Verification
1. **Failing Test First (RED):** Authored initial tests in `tests/test_ipc.py`. Ran pytest against un-modified `main.py` and `daemon.py`:
   - Tests failed due to missing newline framing, hardcoded socket paths connecting to dead legacy sockets, and missing connection reset handling.
2. **Implementation (GREEN):** Implemented newline-delimited JSON stream framing and signal lifecycle management in `voice_flow/main.py` and `voice_flow/daemon.py`.
3. **Passing Verification:** Ran `/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_ipc.py`. All 6 tests passed cleanly in 0.30s.

```
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/gishant-singh/Dev/tools/voice-flow
configfile: pyproject.toml
plugins: anyio-4.14.2
collected 6 items

tests/test_ipc.py ......                                                 [100%]

============================== 6 passed in 0.30s ===============================
```

Regression verification across all test suites:
- `tests/test_paths.py`: 4 passed
- `tests/test_recorder.py`: 9 passed
- `tests/test_injector.py`: 10 passed
- `tests/test_hotkey.py`: 12 passed
- `tests/test_ipc.py`: 6 passed
Total: 41 passed across all test files.

## 4. Key Takeaways & Operational Safety
- **No Truncation / Chunking Bugs:** Newline-delimited framing ensures arbitrary payload sizes can be streamed without relying on fixed socket buffer boundaries or risking split JSON tokens.
- **Clean Service Shutdown:** Integration with `systemd` user units via `SIGTERM` is now fully supported. Stopping the service cleanly stops background evdev listeners and deletes the domain socket.
- **Fail-Safe Socket Binding:** The daemon guarantees any orphaned socket left behind by a hard kill (`SIGKILL`) is automatically unlinked prior to re-binding on daemon startup.
