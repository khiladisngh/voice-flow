from unittest.mock import MagicMock, call, patch

from voice_flow.injector import TextInjector

# The autouse ``isolate_desktop_session`` fixture in conftest.py replaces
# evdev.UInput and both clipboard helpers, so nothing here opens /dev/uinput,
# synthesizes a keystroke, or touches the real clipboard.


def test_injector_singleton_device_and_restore():
    injector = TextInjector(restore_clipboard=False)
    assert injector.ui is not None
    original_ui = injector.ui

    # Test pasting does not destroy or close the persistent device
    result = injector.paste("Unit test paste string")
    assert result is True
    assert injector.ui is not None
    assert injector.ui is original_ui

    injector.close()
    assert injector.ui is None


def test_injector_device_persistence_across_multiple_pastes():
    with patch("voice_flow.injector.TextInjector._set_clipboard"):
        injector = TextInjector(restore_clipboard=False)
        assert injector.ui is not None
        device_id = id(injector.ui)

        res1 = injector.paste("first")
        res2 = injector.paste("second")
        res3 = injector.paste("third")

        assert res1 is True
        assert res2 is True
        assert res3 is True
        assert id(injector.ui) == device_id
        injector.close()
        assert injector.ui is None


def test_injector_close_is_idempotent():
    injector = TextInjector(restore_clipboard=False)
    assert injector.ui is not None
    injector.close()
    assert injector.ui is None
    # Calling close again should not raise
    injector.close()
    assert injector.ui is None


def test_injector_reinitializes_if_device_is_none():
    injector = TextInjector(restore_clipboard=False)
    injector.close()
    assert injector.ui is None

    # Paste should re-init uinput
    with patch("voice_flow.injector.TextInjector._set_clipboard"):
        res = injector.paste("reinit test")
        assert res is True
        assert injector.ui is not None
        injector.close()


def test_injector_paste_empty_text_returns_false():
    injector = TextInjector(restore_clipboard=False)
    assert injector.paste("") is False
    assert injector.paste(None) is False
    injector.close()


def test_injector_paste_exception_resets_device():
    injector = TextInjector(restore_clipboard=False)
    assert injector.ui is not None
    mock_ui = MagicMock()
    mock_ui.write.side_effect = OSError("Virtual device disconnected")
    injector.ui = mock_ui

    with patch("voice_flow.injector.TextInjector._set_clipboard"):
        res = injector.paste("fail test")
        assert res is False
        # Device should be closed and set to None
        assert injector.ui is None
        mock_ui.close.assert_called_once()


def test_injector_clipboard_restore_window_and_success_condition():
    with (
        patch("voice_flow.injector.TextInjector._get_current_clipboard", return_value=b"old-data"),
        patch("voice_flow.injector.TextInjector._set_clipboard") as mock_set,
        patch("voice_flow.injector.time.sleep") as mock_sleep,
    ):
        injector = TextInjector(restore_clipboard=True)
        # Mock ui so write succeeds
        mock_ui = MagicMock()
        injector.ui = mock_ui

        res = injector.paste("new-data")
        assert res is True

        # First set was new-data
        mock_set.assert_any_call(b"new-data")
        # Restored old-data
        mock_set.assert_any_call(b"old-data")
        # Assert sleep(0.35) was called for clipboard restore window
        mock_sleep.assert_any_call(0.35)
        injector.close()


def test_injector_clipboard_not_restored_on_failure():
    with (
        patch("voice_flow.injector.TextInjector._get_current_clipboard", return_value=b"old-data"),
        patch("voice_flow.injector.TextInjector._set_clipboard") as mock_set,
        patch("voice_flow.injector.time.sleep") as mock_sleep,
    ):
        injector = TextInjector(restore_clipboard=True)
        # Mock ui write failure
        mock_ui = MagicMock()
        mock_ui.write.side_effect = RuntimeError("uinput write failed")
        injector.ui = mock_ui

        res = injector.paste("new-data")
        assert res is False

        # new-data was copied
        mock_set.assert_called_once_with(b"new-data")
        # old-data was NOT restored because paste failed
        assert not any(c == call(b"old-data") for c in mock_set.call_args_list)
        # sleep(0.35) was NOT called
        assert not any(c == call(0.35) for c in mock_sleep.call_args_list)


def test_injector_context_manager():
    with TextInjector(restore_clipboard=False) as injector:
        assert injector.ui is not None
        mock_close = MagicMock(wraps=injector.ui.close)
        injector.ui.close = mock_close
    assert injector.ui is None
    mock_close.assert_called_once()


def test_injector_init_failure_handled_gracefully(capsys):
    with patch("voice_flow.injector.evdev.UInput", side_effect=PermissionError("Permission denied")):
        injector = TextInjector(restore_clipboard=False)
        assert injector.ui is None
        res = injector.paste("fail")
        assert res is False
        injector.close()
        assert injector.ui is None
    captured = capsys.readouterr()
    assert "Failed to initialize uinput device" in captured.out
    assert "Cannot paste: virtual keyboard unavailable" in captured.out
