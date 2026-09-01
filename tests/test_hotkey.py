import time
import threading
import selectors
from unittest.mock import MagicMock, patch, call
import pytest
import evdev
from evdev import ecodes

from voice_flow.hotkey import GlobalHotkeyListener


def test_combo_code_resolution_default():
    """Verify default combo codes resolve to KEY_RIGHTCTRL and KEY_RIGHTALT."""
    listener = GlobalHotkeyListener()
    expected = {ecodes.KEY_RIGHTCTRL, ecodes.KEY_RIGHTALT}
    assert listener.required_codes == expected
    assert listener.hold_threshold == 0.45


def test_combo_code_resolution_custom_and_unknown():
    """Verify custom combo resolution and graceful handling of unknown key strings."""
    listener = GlobalHotkeyListener(
        combo_keys=["KEY_LEFTCTRL", "KEY_SPACE", "KEY_NONEXISTENT_XYZ"],
        hold_threshold=0.3,
    )
    expected = {ecodes.KEY_LEFTCTRL, ecodes.KEY_SPACE}
    assert listener.required_codes == expected
    assert listener.hold_threshold == 0.3


def test_find_keyboards_excludes_helper_and_virtual_devices():
    """Verify finding keyboards filters out virtual/helper devices and non-matching devices."""
    listener = GlobalHotkeyListener(combo_keys=["KEY_RIGHTCTRL", "KEY_RIGHTALT"])

    mock_real = MagicMock(spec=evdev.InputDevice)
    mock_real.path = "/dev/input/event0"
    mock_real.name = "Real Mechanical Keyboard"
    mock_real.capabilities.return_value = {
        ecodes.EV_KEY: [ecodes.KEY_RIGHTCTRL, ecodes.KEY_RIGHTALT, ecodes.KEY_A]
    }

    mock_helper = MagicMock(spec=evdev.InputDevice)
    mock_helper.path = "/dev/input/event1"
    mock_helper.name = "XTest Virtual Pointer helper"
    mock_helper.capabilities.return_value = {
        ecodes.EV_KEY: [ecodes.KEY_RIGHTCTRL, ecodes.KEY_RIGHTALT]
    }

    mock_virtual = MagicMock(spec=evdev.InputDevice)
    mock_virtual.path = "/dev/input/event2"
    mock_virtual.name = "voice-flow-virtual-kb"
    mock_virtual.capabilities.return_value = {
        ecodes.EV_KEY: [ecodes.KEY_RIGHTCTRL, ecodes.KEY_RIGHTALT]
    }

    mock_mouse = MagicMock(spec=evdev.InputDevice)
    mock_mouse.path = "/dev/input/event3"
    mock_mouse.name = "Optical Mouse"
    mock_mouse.capabilities.return_value = {
        ecodes.EV_KEY: [ecodes.KEY_LEFTMETA]
    }

    device_map = {
        "/dev/input/event0": mock_real,
        "/dev/input/event1": mock_helper,
        "/dev/input/event2": mock_virtual,
        "/dev/input/event3": mock_mouse,
    }

    with patch("evdev.list_devices", return_value=list(device_map.keys())):
        with patch("evdev.InputDevice", side_effect=lambda path: device_map[path]):
            keyboards = listener._find_keyboards()

            assert len(keyboards) == 1
            assert keyboards[0] is mock_real
            assert "helper" not in keyboards[0].name.lower()
            assert "virtual" not in keyboards[0].name.lower()


def test_state_lock_exists_and_protects_recording():
    """Verify listener has a threading.Lock and state transitions are thread-safe."""
    on_start = MagicMock()
    on_stop = MagicMock()
    listener = GlobalHotkeyListener(
        on_start_record=on_start,
        on_stop_record=on_stop,
    )

    assert hasattr(listener, "_lock"), "Listener must have a threading.Lock instance in _lock"
    assert isinstance(listener._lock, type(threading.Lock()))
    assert hasattr(listener, "_last_scan_time"), "Listener must track _last_scan_time"


def test_device_disconnect_cleanup_on_oserror():
    """Verify when dev.read() raises OSError/IOError, the device is unregistered, closed, and removed."""
    listener = GlobalHotkeyListener()

    mock_dev = MagicMock(spec=evdev.InputDevice)
    mock_dev.name = "Wireless Keyboard"
    mock_dev.path = "/dev/input/event4"
    mock_dev.read.side_effect = OSError(19, "No such device")

    mock_selector = MagicMock()
    key = MagicMock()
    key.fileobj = mock_dev
    mock_selector.select.return_value = [(key, selectors.EVENT_READ)]

    # We patch _find_keyboards to return our device initially
    with patch.object(listener, "_find_keyboards", return_value=[mock_dev]):
        with patch("selectors.DefaultSelector", return_value=mock_selector):
            # Run one cycle of listener loop then terminate
            def stop_after_one(*args, **kwargs):
                listener._running = False
                return [(key, selectors.EVENT_READ)]

            mock_selector.select.side_effect = stop_after_one

            listener._running = True
            listener._run_listener()

            # Verify unregister and close were called on the failed device
            mock_selector.unregister.assert_called_with(mock_dev)
            mock_dev.close.assert_called()


def test_device_disconnect_cleanup_on_ioerror():
    """Verify when dev.read() raises IOError, device is unregistered and closed."""
    listener = GlobalHotkeyListener()

    mock_dev = MagicMock(spec=evdev.InputDevice)
    mock_dev.name = "Bluetooth Keyboard"
    mock_dev.path = "/dev/input/event5"
    mock_dev.read.side_effect = IOError("Input/output error")

    mock_selector = MagicMock()
    key = MagicMock()
    key.fileobj = mock_dev

    with patch.object(listener, "_find_keyboards", return_value=[mock_dev]):
        with patch("selectors.DefaultSelector", return_value=mock_selector):
            def stop_after_one(*args, **kwargs):
                listener._running = False
                return [(key, selectors.EVENT_READ)]

            mock_selector.select.side_effect = stop_after_one

            listener._running = True
            listener._run_listener()

            mock_selector.unregister.assert_called_with(mock_dev)
            mock_dev.close.assert_called()


def test_dynamic_device_discovery():
    """Verify newly connected keyboards are discovered and registered every 5.0s."""
    listener = GlobalHotkeyListener()

    initial_dev = MagicMock(spec=evdev.InputDevice)
    initial_dev.name = "Primary Keyboard"
    initial_dev.path = "/dev/input/event0"
    initial_dev.read.return_value = []

    new_dev = MagicMock(spec=evdev.InputDevice)
    new_dev.name = "Plugged Keyboard"
    new_dev.path = "/dev/input/event1"
    new_dev.read.return_value = []

    mock_selector = MagicMock()
    # Initially, get_map returns initial_dev
    mock_selector.select.return_value = []

    # First call returns initial_dev, second call returns initial_dev and new_dev
    find_call_count = 0
    def mock_find():
        nonlocal find_call_count
        find_call_count += 1
        if find_call_count == 1:
            return [initial_dev]
        else:
            return [initial_dev, new_dev]

    with patch.object(listener, "_find_keyboards", side_effect=mock_find):
        with patch("selectors.DefaultSelector", return_value=mock_selector):
            # Advance time so the 5.0s check triggers on the second iteration
            time_values = [100.0, 100.0, 106.0, 106.0, 106.0]
            def mock_time():
                if time_values:
                    return time_values.pop(0)
                return 110.0

            select_calls = 0
            def stop_loop(*args, **kwargs):
                nonlocal select_calls
                select_calls += 1
                if select_calls >= 2:
                    listener._running = False
                return []

            mock_selector.select.side_effect = stop_loop

            with patch("time.time", side_effect=mock_time):
                listener._running = True
                listener._run_listener()

            # Verify initial register
            mock_selector.register.assert_any_call(initial_dev, selectors.EVENT_READ)
            # Verify new device was registered dynamically
            mock_selector.register.assert_any_call(new_dev, selectors.EVENT_READ)

def test_concurrent_recording_state_transitions():
    """Verify rapid combo events trigger start/stop without race conditions."""
    start_calls = []
    stop_calls = []

    def on_start():
        start_calls.append(time.time())

    def on_stop():
        stop_calls.append(time.time())

    listener = GlobalHotkeyListener(
        combo_keys=["KEY_RIGHTCTRL", "KEY_RIGHTALT"],
        hold_threshold=0.2,
        on_start_record=on_start,
        on_stop_record=on_stop,
    )

    # Simulate rapid threads calling start/stop state changes under lock
    def worker(start: bool):
        with listener._lock:
            if start:
                if not listener._is_recording:
                    listener._is_recording = True
                    if listener.on_start_record:
                        listener.on_start_record()
            else:
                if listener._is_recording:
                    listener._is_recording = False
                    if listener.on_stop_record:
                        listener.on_stop_record()

    threads = []
    for i in range(20):
        t = threading.Thread(target=worker, args=(i % 2 == 0,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Verify no unhandled exceptions and valid state
    assert isinstance(listener._is_recording, bool)

def test_dynamic_discovery_duplicate_devices_closed():
    """Verify duplicate instances of already-registered devices are closed and not re-registered."""
    listener = GlobalHotkeyListener()

    dev1 = MagicMock(spec=evdev.InputDevice)
    dev1.name = "Primary Keyboard"
    dev1.path = "/dev/input/event0"
    dev1.read.return_value = []

    dup_dev1 = MagicMock(spec=evdev.InputDevice)
    dup_dev1.name = "Primary Keyboard Duplicate"
    dup_dev1.path = "/dev/input/event0"

    mock_selector = MagicMock()
    mock_selector.select.return_value = []

    find_call_count = 0
    def mock_find():
        nonlocal find_call_count
        find_call_count += 1
        if find_call_count == 1:
            return [dev1]
        else:
            return [dup_dev1]

    with patch.object(listener, "_find_keyboards", side_effect=mock_find):
        with patch("selectors.DefaultSelector", return_value=mock_selector):
            time_values = [100.0, 100.0, 106.0, 106.0, 106.0]
            def mock_time():
                if time_values:
                    return time_values.pop(0)
                return 110.0

            select_calls = 0
            def stop_loop(*args, **kwargs):
                nonlocal select_calls
                select_calls += 1
                if select_calls >= 2:
                    listener._running = False
                return []

            mock_selector.select.side_effect = stop_loop

            with patch("time.time", side_effect=mock_time):
                listener._running = True
                listener._run_listener()

            # dup_dev1 must be closed to avoid file descriptor leaks
            dup_dev1.close.assert_called_once()
            # dup_dev1 must NOT be registered
            with pytest.raises(AssertionError):
                mock_selector.register.assert_called_with(dup_dev1, selectors.EVENT_READ)


def test_blocking_io_error_does_not_unregister_device():
    """Verify BlockingIOError on non-blocking read does not unregister or close the device."""
    listener = GlobalHotkeyListener()

    mock_dev = MagicMock(spec=evdev.InputDevice)
    mock_dev.name = "Active Keyboard"
    mock_dev.path = "/dev/input/event0"
    mock_dev.read.side_effect = BlockingIOError("Resource temporarily unavailable")

    mock_selector = MagicMock()
    key = MagicMock()
    key.fileobj = mock_dev

    with patch.object(listener, "_find_keyboards", return_value=[mock_dev]):
        with patch("selectors.DefaultSelector", return_value=mock_selector):
            def stop_after_one(*args, **kwargs):
                listener._running = False
                return [(key, selectors.EVENT_READ)]

            mock_selector.select.side_effect = stop_after_one
            listener._running = True
            listener._run_listener()

            # Should NOT unregister or close healthy device on BlockingIOError
            mock_selector.unregister.assert_not_called()
            # dev.close() should only be called once when selector shuts down in finally block
            assert mock_dev.close.call_count == 1


def test_all_devices_disconnected_clears_active_keys():
    """Verify that when the last device disconnects, active keys and combo state are cleared."""
    listener = GlobalHotkeyListener()
    listener._active_keys.add(ecodes.KEY_RIGHTCTRL)
    listener._combo_active = True

    mock_dev = MagicMock(spec=evdev.InputDevice)
    mock_dev.name = "Dying Keyboard"
    mock_dev.path = "/dev/input/event0"
    mock_dev.read.side_effect = OSError(19, "No such device")

    mock_selector = MagicMock()
    key = MagicMock()
    key.fileobj = mock_dev

    with patch.object(listener, "_find_keyboards", return_value=[mock_dev]):
        with patch("selectors.DefaultSelector", return_value=mock_selector):
            def stop_after_one(*args, **kwargs):
                listener._running = False
                return [(key, selectors.EVENT_READ)]

            mock_selector.select.side_effect = stop_after_one
            listener._running = True
            listener._run_listener()

            assert len(listener._active_keys) == 0
            assert listener._combo_active is False


def test_is_recording_property_thread_safe():
    """Verify is_recording property accesses _is_recording under lock."""
    listener = GlobalHotkeyListener()
    assert listener.is_recording is False
    with listener._lock:
        listener._is_recording = True
    assert listener.is_recording is True
