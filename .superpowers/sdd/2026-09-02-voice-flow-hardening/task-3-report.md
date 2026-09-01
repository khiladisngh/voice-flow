# Task 3 Report: Persistent UInput & Wayland Injection Hardening

## 1. Overview
Task 3 addressed virtual keyboard device creation thrash and Wayland clipboard race conditions in `TextInjector`. Previously, `TextInjector.paste()` instantiated and destroyed an `evdev.UInput` device on every paste invocation. This caused kernel seat reconfigurations, udev device notification thrash, and 40–80ms of unnecessary latency per paste. Furthermore, the previous 120ms clipboard restoration window was too brief for Wayland compositors and complex applications (e.g. Electron/Chromium, Firefox, terminals), causing the previous clipboard contents to clobber the paste payload before the application consumed the data offer.

`TextInjector` now maintains a persistent virtual keyboard instance (`self.ui`), provides a robust and idempotent `close()` method with `try...finally` guarantees, automatically attempts device re-initialization if needed, resets the device on injection error, expands the clipboard restore delay to 350ms, and only restores the clipboard when injection actually succeeds.

## 2. Implementation Summary

### Modified Files
- `voice_flow/injector.py`:
  - `__init__(restore_clipboard: bool = True)`:
    - Initializes `self.ui: Optional[evdev.UInput] = None`.
    - Invokes `self._init_uinput()` to pre-warm the virtual keyboard device.
  - `_init_uinput()`:
    - Instantiates `evdev.UInput(name="voice-flow-virtual-kb")`.
    - Sleeps 50ms (`time.sleep(0.05)`) to permit the Wayland compositor/udev/libinput to assign the virtual device to the seat.
    - Gracefully catches exceptions (e.g. `PermissionError`, missing `/dev/uinput`), leaving `self.ui = None` without crashing initialization.
  - `close()`:
    - Closes `self.ui` if present.
    - Uses `try...finally` to guarantee `self.ui = None` even if `self.ui.close()` raises an exception.
    - Idempotent: safe to call repeatedly.
  - `__enter__`, `__exit__`, `__del__`:
    - Context manager and garbage-collection hooks for deterministic teardown.
  - `paste(text: str) -> bool`:
    - Validates input: immediately returns `False` if `not text`.
    - Saves `old_clipboard` if `self.restore_clipboard` is `True`.
    - Sets Wayland clipboard with `text.encode("utf-8")`.
    - If `self.ui is None`, attempts `_init_uinput()`; returns `False` if device initialization fails.
    - Injects `Ctrl+V` keypresses (`KEY_LEFTCTRL`, `KEY_V`) with synchronizations (`ui.syn()`).
    - Catches exceptions during injection, calls `self.close()` to reset device state, and marks `success = False`.
    - Only restores `old_clipboard` after a 350ms (`time.sleep(0.35)`) delay if `success` is `True`, `self.restore_clipboard` is `True`, and `old_clipboard` is present.
    - Returns `True` on success and `False` on failure.

### Created Files
- `tests/test_injector.py`:
  - `test_injector_singleton_device_and_restore`: Verifies persistent device initialization and reuse across paste and close.
  - `test_injector_device_persistence_across_multiple_pastes`: Verifies the identical `UInput` instance is retained across successive `paste()` calls.
  - `test_injector_close_is_idempotent`: Verifies `close()` can be called repeatedly without raising exceptions.
  - `test_injector_reinitializes_if_device_is_none`: Verifies `paste()` recovers and re-creates device if `self.ui` was closed or `None`.
  - `test_injector_paste_empty_text_returns_false`: Verifies empty or `None` text input returns `False`.
  - `test_injector_paste_exception_resets_device`: Verifies injection errors reset the virtual keyboard and return `False`.
  - `test_injector_clipboard_restore_window_and_success_condition`: Verifies 350ms sleep window and restoration of `old_clipboard` on successful injection.
  - `test_injector_clipboard_not_restored_on_failure`: Verifies clipboard is not restored if injection fails.
  - `test_injector_context_manager`: Verifies `with TextInjector() as injector:` closes device upon exit.
  - `test_injector_init_failure_handled_gracefully`: Verifies initialization failure (e.g. permission error) leaves `self.ui = None` gracefully without unhandled exception.

## 3. TDD Process & Verification
1. **Failing Test First (RED):** Authored unit tests in `tests/test_injector.py` reflecting the design requirements. Ran pytest against the un-modified `injector.py`, confirming 9 expected test failures (`AttributeError: 'TextInjector' object has no attribute 'ui'`, `AttributeError: 'TextInjector' object has no attribute 'close'`, `AssertionError: assert None is False`, `TypeError: 'TextInjector' object does not support the context manager protocol`).
2. **Implementation (GREEN):** Updated `voice_flow/injector.py` with persistent `UInput`, exception recovery, `close()` teardown, 350ms clipboard delay, and boolean return values.
3. **Passing Verification:** Ran `/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_injector.py`. All 10 tests passed cleanly.

```
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/gishant-singh/Dev/tools/voice-flow
configfile: pyproject.toml
plugins: anyio-4.14.2
collected 10 items

tests/test_injector.py ..........                                        [100%]

============================== 10 passed in 1.87s ==============================
```

## 4. Resource Lifecycle & Wayland Compatibility Resolution
- **Kernel Device Thrash:** By reusing a single persistent `UInput` virtual keyboard instance, the daemon no longer creates and unregisters kernel input devices on every speech segment. This eliminates kernel log churn and reduces end-to-end injection latency.
- **Wayland Data Offer Synchronization:** Wayland's clipboard architecture transfers selection data asynchronously on demand via pipe file descriptors when a client pastes. Increasing the restore window to 350ms ensures complex GUI clients have finished negotiating and reading the data offer before `wl-copy` restores the prior clipboard.
- **Safe Failure Modes:** If injection fails or the kernel device disconnects, the injector tears down the device and leaves the transcribed text in the clipboard so the user can still manually paste (`Ctrl+V`), avoiding text loss.
