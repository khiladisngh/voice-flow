import time
import subprocess
from typing import Optional
import evdev
from evdev import ecodes

class TextInjector:
    def __init__(self, restore_clipboard: bool = True):
        self.restore_clipboard = restore_clipboard

    def _get_current_clipboard(self) -> Optional[bytes]:
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

    def paste(self, text: str):
        """Copies text to Wayland clipboard, simulates Ctrl+V, and restores previous clipboard."""
        if not text:
            return

        old_clipboard = self._get_current_clipboard() if self.restore_clipboard else None

        # Copy new text to clipboard
        self._set_clipboard(text.encode("utf-8"))

        # Inject Ctrl+V via uinput virtual keyboard
        try:
            ui = evdev.UInput(name="voice-flow-virtual-kb")
            time.sleep(0.04)
            ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
            ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
            ui.syn()
            time.sleep(0.02)
            ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
            ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
            ui.syn()
            ui.close()
        except Exception as e:
            # If uinput fails for any reason, user still has text in clipboard
            pass

        # Give the target application time to consume clipboard before restoring
        if old_clipboard is not None:
            time.sleep(0.12)
            self._set_clipboard(old_clipboard)
