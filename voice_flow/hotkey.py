import time
import threading
import selectors
from typing import List, Callable, Optional, Set
import evdev
from evdev import ecodes

class GlobalHotkeyListener:
    def __init__(
        self,
        combo_keys: Optional[List[str]] = None,
        hold_threshold: float = 0.45,
        on_start_record: Optional[Callable[[], None]] = None,
        on_stop_record: Optional[Callable[[], None]] = None,
    ):
        if combo_keys is None:
            combo_keys = ["KEY_RIGHTCTRL", "KEY_RIGHTALT"]

        self.required_codes: Set[int] = {
            getattr(ecodes, k) for k in combo_keys if hasattr(ecodes, k)
        }
        self.hold_threshold = hold_threshold
        self.on_start_record = on_start_record
        self.on_stop_record = on_stop_record

        self._active_keys: Set[int] = set()
        self._combo_active = False
        self._combo_press_time = 0.0
        self._is_recording = False
        self._tap_started_recording = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _find_keyboards(self) -> List[evdev.InputDevice]:
        keyboards = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    # Must support at least one of the target keys
                    if any(k in keys for k in self.required_codes):
                        name = dev.name.lower()
                        if "helper" not in name and "virtual" not in name:
                            keyboards.append(dev)
            except Exception:
                pass
        return keyboards

    def _run_listener(self):
        selector = selectors.DefaultSelector()
        devices = self._find_keyboards()

        if not devices:
            print("[Hotkey] No suitable keyboard devices found for global hotkeys.")
            return

        for dev in devices:
            try:
                selector.register(dev, selectors.EVENT_READ)
                print(f"[Hotkey] Listening to keyboard: {dev.name} ({dev.path})")
            except Exception as e:
                print(f"[Hotkey] Failed to register {dev.name}: {e}")

        key_names = [ecodes.KEY.get(c, str(c)) for c in self.required_codes]
        print(f"[Hotkey] Active global combo: {' + '.join(key_names)}")

        while self._running:
            try:
                events = selector.select(timeout=0.3)
                for key, _ in events:
                    dev = key.fileobj
                    for event in dev.read():
                        if event.type != ecodes.EV_KEY:
                            continue

                        # event.value: 0=up, 1=down, 2=hold
                        if event.code in self.required_codes:
                            if event.value in (1, 2):
                                self._active_keys.add(event.code)
                            elif event.value == 0:
                                self._active_keys.discard(event.code)

                            # Check if the full combo is currently down
                            combo_pressed = self.required_codes.issubset(self._active_keys)

                            if combo_pressed and not self._combo_active:
                                # Combo freshly triggered
                                self._combo_active = True
                                self._combo_press_time = time.time()

                                if not self._is_recording:
                                    # Start recording
                                    self._is_recording = True
                                    self._tap_started_recording = True
                                    if self.on_start_record:
                                        threading.Thread(target=self.on_start_record, daemon=True).start()
                                else:
                                    # Already recording -> this press begins the "toggle stop"
                                    self._tap_started_recording = False

                            elif not combo_pressed and self._combo_active:
                                # Combo was released
                                self._combo_active = False
                                press_duration = time.time() - self._combo_press_time

                                if press_duration >= self.hold_threshold:
                                    # Push-to-Talk release: stop recording now
                                    if self._is_recording:
                                        self._is_recording = False
                                        if self.on_stop_record:
                                            threading.Thread(target=self.on_stop_record, daemon=True).start()
                                else:
                                    # Quick tap release
                                    if not self._tap_started_recording:
                                        # This was the second tap to stop
                                        if self._is_recording:
                                            self._is_recording = False
                                            if self.on_stop_record:
                                                threading.Thread(target=self.on_stop_record, daemon=True).start()
                                    else:
                                        # First tap: keep recording, clear flag so next tap stops
                                        self._tap_started_recording = False

            except Exception:
                time.sleep(0.05)

        selector.close()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_listener, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
