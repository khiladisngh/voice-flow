# Task 4 Report: Hotkey Resiliency & Dynamic Device Discovery

## 1. Overview
Task 4 addresses reliability, dynamic hotplug discovery, and concurrency safety in `GlobalHotkeyListener` (`voice_flow/hotkey.py`). Previously, `GlobalHotkeyListener`:
1. Swallowed `OSError` exceptions in an outer broad `try...except Exception` during event polling, causing an infinite 50ms CPU spin loop when a wireless keyboard disconnected or entered sleep mode because the dead file descriptor remained registered in `DefaultSelector`.
2. Failed to discover newly connected or woken keyboards post-startup, exiting immediately if no keyboard was detected on launch.
3. Leaked file descriptors if devices were re-opened during device detection.
4. Lacked thread locking around recording state transitions (`_is_recording`, `on_start_record`, `on_stop_record`), opening race conditions between rapid multi-key events and daemon thread triggers.

`GlobalHotkeyListener` now catches `(OSError, IOError)` on device reads, cleans up and unregisters disconnected devices, executes a periodic 5.0-second dynamic device discovery loop, prevents descriptor leaks by closing duplicates, and protects recording state transitions with a dedicated `threading.Lock()`.

## 2. Implementation Summary

### Modified Files
- `voice_flow/hotkey.py`:
  - `__init__(...)`:
    - Added `self._lock = threading.Lock()` for atomic state transitions.
    - Added `self._last_scan_time: float = 0.0` to schedule periodic discovery scans.
  - `is_recording`:
    - Exposed thread-safe property acquiring `self._lock` when reading `self._is_recording`.
  - `_run_listener()`:
    - Maintains `active_devices: List[evdev.InputDevice]` to track live registered devices.
    - Does not exit if no initial keyboards are detected; logs an informational warning and enters the polling loop to allow dynamic discovery when wireless keyboards wake up.
    - Added periodic dynamic device discovery check every 5.0 seconds (`now - self._last_scan_time >= 5.0`):
      - Scans `/dev/input` via `self._find_keyboards()`.
      - Identifies newly attached/woken keyboards not in `registered_paths`.
      - Registers new keyboards with `selector.register(dev, selectors.EVENT_READ)` and appends to `active_devices`.
      - Explicitly calls `dev.close()` on candidate devices whose paths are already registered, preventing file descriptor leaks.
    - Hardened read event loop:
      - Ignores `BlockingIOError` (non-blocking read when no events are queued).
      - Catches `(OSError, IOError)`: logs the disconnect/error, unregisters `dev` from `selector`, calls `dev.close()`, and removes `dev` from `active_devices`.
      - Clears `self._active_keys` and `self._combo_active` if all devices disconnect, preventing stuck key states.
    - Guarded combo triggered (`combo_pressed and not self._combo_active`) and combo released (`not combo_pressed and self._combo_active`) state transitions under `with self._lock:`.
    - Added `finally:` block to guarantee all `dev.close()` and `selector.close()` cleanup runs on listener shutdown.

### Created Files
- `tests/test_hotkey.py`:
  - `test_combo_code_resolution_default`: Verifies default combo resolves to `{ecodes.KEY_RIGHTCTRL, ecodes.KEY_RIGHTALT}` with 0.45s hold threshold.
  - `test_combo_code_resolution_custom_and_unknown`: Verifies custom combo strings resolve properly and unknown key names are safely ignored.
  - `test_find_keyboards_excludes_helper_and_virtual_devices`: Verifies filtering excludes devices with "helper" or "virtual" in name and non-matching devices.
  - `test_state_lock_exists_and_protects_recording`: Verifies `_lock` is a `threading.Lock` instance and `_last_scan_time` is initialized.
  - `test_device_disconnect_cleanup_on_oserror`: Verifies `OSError` on `dev.read()` triggers `selector.unregister(dev)`, `dev.close()`, and active list removal.
  - `test_device_disconnect_cleanup_on_ioerror`: Verifies `IOError` triggers clean device unregistration and closure.
  - `test_dynamic_device_discovery`: Verifies keyboards plugged in after startup are discovered and registered during the 5.0-second periodic scan.
  - `test_concurrent_recording_state_transitions`: Verifies thread safety during rapid start/stop toggles under `_lock`.
  - `test_dynamic_discovery_duplicate_devices_closed`: Verifies duplicates of already-registered devices are closed immediately to prevent fd leaks.
  - `test_blocking_io_error_does_not_unregister_device`: Verifies `BlockingIOError` does not falsely trigger device removal.
  - `test_all_devices_disconnected_clears_active_keys`: Verifies active modifier keys and combo state are cleared when all devices disconnect.
  - `test_is_recording_property_thread_safe`: Verifies `is_recording` property safely reads state under lock.

## 3. TDD Process & Verification
1. **Failing Test First (RED):** Authored initial tests in `tests/test_hotkey.py`. Ran pytest against the un-modified `hotkey.py`:
   - 4 tests failed as expected (`AssertionError: Listener must have a threading.Lock instance in _lock`, `Expected: unregister(...) Actual: not called` for `OSError` and `IOError`, and missing dynamic registration).
2. **Implementation (GREEN):** Implemented error recovery, unregistration, dynamic discovery, and state locking in `voice_flow/hotkey.py`.
3. **Passing Verification:** Ran `/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_hotkey.py`. All 12 tests passed cleanly.

```
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/gishant-singh/Dev/tools/voice-flow
configfile: pyproject.toml
plugins: anyio-4.14.2
collected 12 items

tests/test_hotkey.py ............                                        [100%]

============================== 12 passed in 0.04s ==============================
```

## 4. Key Takeaways & Operational Safety
- **No CPU Spin on Disconnect:** Previously, when a sleeping keyboard dropped off `/dev/input`, `selector.select()` returned immediately on the dead fd, causing 100% CPU usage on a 50ms polling loop. Disconnected devices are now immediately unregistered and closed.
- **Dynamic Hotplug Support:** Wireless keyboards that go into deep sleep or USB keyboards plugged in after system boot are automatically detected and registered within 5.0 seconds without restarting the daemon.
- **Resource Discipline:** Any duplicate input devices opened during periodic scans are closed immediately, guaranteeing zero file descriptor leakage over long-running sessions.
- **Concurrency Safety:** The recording state transition lock eliminates race conditions between rapid double-tap releases and push-to-talk holds.
