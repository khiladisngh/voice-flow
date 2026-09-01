import selectors
import threading
import time
from collections.abc import Callable

import evdev
from evdev import ecodes


class GlobalHotkeyListener:
    def __init__(
        self,
        combo_keys: list[str] | None = None,
        hold_threshold: float = 0.45,
        on_start_record: Callable[[], None] | None = None,
        on_stop_record: Callable[[], None] | None = None,
    ):
        if combo_keys is None:
            combo_keys = ["KEY_RIGHTCTRL", "KEY_RIGHTALT"]

        self.required_codes: set[int] = {getattr(ecodes, k) for k in combo_keys if hasattr(ecodes, k)}
        self.hold_threshold = hold_threshold
        self.on_start_record = on_start_record
        self.on_stop_record = on_stop_record

        self._active_keys: set[int] = set()
        self._combo_active = False
        self._combo_press_time = 0.0
        self._is_recording = False
        self._tap_started_recording = False
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_scan_time: float = 0.0

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._is_recording

    def _find_keyboards(self) -> list[evdev.InputDevice]:
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
        self._last_scan_time = time.time()
        active_devices: list[evdev.InputDevice] = []

        devices = self._find_keyboards()
        for dev in devices:
            try:
                selector.register(dev, selectors.EVENT_READ)
                active_devices.append(dev)
                print(f"[Hotkey] Listening to keyboard: {dev.name} ({dev.path})")
            except Exception as e:
                print(f"[Hotkey] Failed to register {dev.name}: {e}")
                try:
                    dev.close()
                except Exception:
                    pass

        if not active_devices:
            print("[Hotkey] No suitable keyboard devices found for global hotkeys.")

        key_names = [ecodes.KEY.get(c, str(c)) for c in self.required_codes]
        print(f"[Hotkey] Active global combo: {' + '.join(key_names)}")

        try:
            while self._running:
                try:
                    # Periodic dynamic discovery every 5.0 seconds
                    now = time.time()
                    if now - self._last_scan_time >= 5.0:
                        self._last_scan_time = now
                        registered_paths = {getattr(d, "path", None) for d in active_devices}
                        for dev in self._find_keyboards():
                            dev_path = getattr(dev, "path", None)
                            if dev_path not in registered_paths:
                                try:
                                    selector.register(dev, selectors.EVENT_READ)
                                    active_devices.append(dev)
                                    registered_paths.add(dev_path)
                                    print(
                                        f"[Hotkey] Discovered and listening to keyboard: {dev.name} ({dev.path})"
                                    )
                                except Exception as e:
                                    print(f"[Hotkey] Failed to register {dev.name}: {e}")
                                    try:
                                        dev.close()
                                    except Exception:
                                        pass
                            else:
                                # Already registered; close duplicate descriptor
                                try:
                                    dev.close()
                                except Exception:
                                    pass

                    events = selector.select(timeout=0.3)
                    for key, _ in events:
                        dev = key.fileobj
                        try:
                            dev_events = list(dev.read())
                        except BlockingIOError:
                            continue
                        except OSError as e:
                            print(
                                f"[Hotkey] Device disconnected or read error ({getattr(dev, 'name', 'unknown')}): {e}"
                            )
                            try:
                                selector.unregister(dev)
                            except Exception:
                                pass
                            try:
                                dev.close()
                            except Exception:
                                pass
                            if dev in active_devices:
                                active_devices.remove(dev)
                            if not active_devices:
                                self._active_keys.clear()
                                self._combo_active = False
                            continue

                        for event in dev_events:
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

                                    with self._lock:
                                        if not self._is_recording:
                                            # Start recording
                                            self._is_recording = True
                                            self._tap_started_recording = True
                                            if self.on_start_record:
                                                threading.Thread(
                                                    target=self.on_start_record, daemon=True
                                                ).start()
                                        else:
                                            # Already recording -> this press begins the "toggle stop"
                                            self._tap_started_recording = False

                                elif not combo_pressed and self._combo_active:
                                    # Combo was released
                                    self._combo_active = False
                                    press_duration = time.time() - self._combo_press_time

                                    with self._lock:
                                        if press_duration >= self.hold_threshold:
                                            # Push-to-Talk release: stop recording now
                                            if self._is_recording:
                                                self._is_recording = False
                                                if self.on_stop_record:
                                                    threading.Thread(
                                                        target=self.on_stop_record, daemon=True
                                                    ).start()
                                        else:
                                            # Quick tap release
                                            if not self._tap_started_recording:
                                                # This was the second tap to stop
                                                if self._is_recording:
                                                    self._is_recording = False
                                                    if self.on_stop_record:
                                                        threading.Thread(
                                                            target=self.on_stop_record, daemon=True
                                                        ).start()
                                            else:
                                                # First tap: keep recording, clear flag so next tap stops
                                                self._tap_started_recording = False

                except Exception:
                    time.sleep(0.05)
        finally:
            for dev in active_devices:
                try:
                    dev.close()
                except Exception:
                    pass
            try:
                selector.close()
            except Exception:
                pass

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_listener, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
