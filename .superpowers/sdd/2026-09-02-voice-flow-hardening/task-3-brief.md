# Task 3: Persistent UInput & Wayland Injection Hardening

## Objective
Make `TextInjector` reuse a single persistent virtual keyboard instance to eliminate kernel device creation thrash, ensure reliable cleanup with a `close()` method and `try...finally`, and increase the clipboard restore window to 350ms to prevent Wayland data offer clobbering.

## Files to touch
- Modify: `voice_flow/injector.py`
- Test: `tests/test_injector.py`

## Requirements
1. In `voice_flow/injector.py`:
   - Initialize `self.ui = None` and call `self._init_uinput()` in `__init__`.
   - Implement `_init_uinput(self)`: creates `evdev.UInput(name="voice-flow-virtual-kb")`.
   - Implement `close(self)`: closes `self.ui` if present, sets `self.ui = None`.
   - In `paste(self, text: str) -> bool`:
     - If `self.ui is None`, attempt `_init_uinput()`.
     - Write keystrokes with `self.ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)`, etc.
     - On exception, call `self.close()` to reset device.
     - Increase clipboard restore sleep to `0.35` seconds (350ms).
     - Only restore `old_clipboard` if injection succeeded and `self.restore_clipboard` is True.
     - Return `True` on success, `False` on failure.
2. Write unit tests in `tests/test_injector.py`:
   - Test injector device persistence across calls.
   - Test `close()` releases device.
   - Run tests with `/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_injector.py`.
   - Commit with git.
