# Task 4: Hotkey Resiliency & Dynamic Device Discovery

## Objective
Harden `GlobalHotkeyListener` against keyboard disconnects (e.g. wireless keyboard sleeping) to prevent infinite 50ms CPU polling loops, enable dynamic hotplug discovery of newly connected keyboards, and prevent audio clobbering via state locking.

## Files to touch
- Modify: `voice_flow/hotkey.py`
- Test: `tests/test_hotkey.py`

## Requirements
1. In `voice_flow/hotkey.py`:
   - When reading events with `dev.read()`, catch `(OSError, IOError)`.
   - On error: unregister `dev` from `selector`, call `dev.close()`, and remove from active list.
   - Maintain `_last_scan_time`. Every 5.0 seconds in the event loop, call `_find_keyboards()` to detect any newly attached/woken keyboards not already in `selector`, and register them.
   - Protect `_is_recording`, `on_start_record`, and `on_stop_record` state transitions with a `threading.Lock()` so rapid key presses or concurrent threads cannot race.
2. Write unit tests in `tests/test_hotkey.py`:
   - Verify keyboard filter excludes helper/virtual devices.
   - Verify combo code resolution.
   - Run tests with `/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_hotkey.py`.
   - Commit with git.
