# Task 2: Reliable Audio Recording & Process Flush

## Objective
Fix the race condition in `AudioRecorder.stop()` where the termination loop breaks prematurely on iteration 0 because `getsize > 44` is already true. Actively poll `os.kill(pid, 0)` until `pw-record` terminates and flushes its buffers. Support unique session recording paths to avoid file clobbering.

## Files to touch
- Modify: `voice_flow/recorder.py`
- Test: `tests/test_recorder.py`

## Requirements
1. In `voice_flow/recorder.py`:
   - `start(session_id: str = "current") -> bool`:
     - Resolve audio path using `voice_flow.paths.get_audio_path(session_id)`.
     - Record process PID to `voice_flow.paths.get_pid_file()`.
     - Store `self.current_audio_path`.
   - `stop(timeout: float = 1.0) -> Optional[str]`:
     - Read PID from PID file.
     - Send `signal.SIGINT` to `pw-record`.
     - Loop with `os.kill(pid, 0)` and `time.sleep(0.02)` until `ProcessLookupError` (up to `timeout` seconds).
     - If timeout is reached, force kill with `signal.SIGKILL`.
     - Remove PID file.
     - Play sound and notification.
     - Return `str(self.current_audio_path)` if it exists and is non-empty, else `None`.
2. Write unit test in `tests/test_recorder.py`:
   - Verify start, recording state, process termination, and non-empty audio path.
   - Run tests with `/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_recorder.py`.
   - Commit with git.
