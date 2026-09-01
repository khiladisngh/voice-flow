import subprocess
import time

import evdev
from evdev import ecodes


class TextInjector:
    def __init__(self, restore_clipboard: bool = True):
        self.restore_clipboard = restore_clipboard
        self.ui: evdev.UInput | None = None
        self._init_uinput()

    def _init_uinput(self):
        try:
            self.ui = evdev.UInput(name="voice-flow-virtual-kb")
            time.sleep(0.05)
        except Exception:
            self.ui = None

    def close(self):
        if self.ui is not None:
            try:
                self.ui.close()
            except Exception:
                pass
            finally:
                self.ui = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    def _get_current_clipboard(self) -> bytes | None:
        try:
            res = subprocess.run(
                ["wl-paste", "--no-newline"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=0.5,
            )
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass
        return None

    def _set_clipboard(self, content: bytes):
        try:
            proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
            proc.communicate(input=content, timeout=1.0)
        except Exception:
            pass

    def paste(self, text: str) -> bool:
        """Copies text to Wayland clipboard, simulates Ctrl+V via persistent uinput device, and restores previous clipboard."""
        if not text:
            return False

        old_clipboard = self._get_current_clipboard() if self.restore_clipboard else None

        # Copy new text to clipboard
        self._set_clipboard(text.encode("utf-8"))

        if self.ui is None:
            self._init_uinput()

        if self.ui is None:
            return False

        success = False
        try:
            time.sleep(0.04)
            self.ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
            self.ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
            self.ui.syn()
            time.sleep(0.02)
            self.ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
            self.ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
            self.ui.syn()
            success = True
        except Exception:
            self.close()
            success = False

        # Wait 350ms to allow target Wayland client to complete data offer consumption
        if self.restore_clipboard and old_clipboard is not None and success:
            time.sleep(0.35)
            self._set_clipboard(old_clipboard)

        return success
