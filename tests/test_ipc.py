import json
import os
import signal
import socket
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from voice_flow.main import send_to_daemon
from voice_flow.paths import get_socket_path


def test_framed_socket_communication(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    sock_path = get_socket_path()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(1)

    received_data = {}

    def server_worker():
        conn, _ = server.accept()
        with conn.makefile("r", encoding="utf-8") as f:
            line = f.readline()
            received_data["line"] = line
            req = json.loads(line)
            received_data["req"] = req
            assert req.get("action") == "ping"
        conn.sendall(json.dumps({"status": "pong"}).encode("utf-8") + b"\n")
        conn.close()
        server.close()

    t = threading.Thread(target=server_worker)
    t.start()

    res = send_to_daemon({"action": "ping"})
    assert res.get("status") == "pong"
    t.join()

    # Verify newline framing was present
    assert received_data["line"].endswith("\n")
    assert received_data["req"] == {"action": "ping"}


def test_send_to_daemon_empty_response_handling(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    sock_path = get_socket_path()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(1)

    def server_worker():
        conn, _ = server.accept()
        # Read the request then close without sending data (EOF)
        with conn.makefile("r", encoding="utf-8") as f:
            _ = f.readline()
        conn.close()
        server.close()

    t = threading.Thread(target=server_worker)
    t.start()
    with pytest.raises(ConnectionResetError, match="Empty response from daemon"):
        send_to_daemon({"action": "ping"})

    t.join()


def test_send_to_daemon_large_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    sock_path = get_socket_path()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(1)

    # 32KB payload - larger than 8KB old buffer
    large_text = "x" * 32768

    def server_worker():
        conn, _ = server.accept()
        with conn.makefile("r", encoding="utf-8") as f:
            line = f.readline()
            req = json.loads(line)
            assert req.get("data") == large_text
        response_payload = {"status": "ok", "echo": large_text}
        conn.sendall(json.dumps(response_payload).encode("utf-8") + b"\n")
        conn.close()
        server.close()

    t = threading.Thread(target=server_worker)
    t.start()

    res = send_to_daemon({"action": "echo", "data": large_text})
    assert res.get("status") == "ok"
    assert res.get("echo") == large_text
    t.join()


def test_send_to_daemon_missing_socket(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    # Socket does not exist
    with pytest.raises(ConnectionError, match="Daemon socket not found"):
        send_to_daemon({"action": "ping"})


@patch("voice_flow.daemon.Transcriber")
@patch("voice_flow.daemon.TextCleaner")
@patch("voice_flow.daemon.TextInjector")
@patch("voice_flow.daemon.AudioRecorder")
@patch("voice_flow.daemon.GlobalHotkeyListener")
def test_daemon_framed_server_loop(
    mock_hotkey_cls,
    mock_recorder_cls,
    mock_injector_cls,
    mock_cleaner_cls,
    mock_transcriber_cls,
    tmp_path,
    monkeypatch,
):
    from voice_flow.daemon import VoiceFlowDaemon

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    sock_path = get_socket_path()

    mock_recorder = MagicMock()
    mock_recorder.is_recording.side_effect = [False, True]
    mock_recorder_cls.return_value = mock_recorder

    mock_hotkey = MagicMock()
    mock_hotkey_cls.return_value = mock_hotkey

    config = {
        "stt": {"device": "cpu", "model_size": "tiny"},
        "cleaner": {"enabled": False},
        "ui": {"restore_clipboard": False},
        "audio": {"temp_file": "auto"},
        "hotkey": {"enabled": True},
    }

    daemon = VoiceFlowDaemon(config)

    # Start daemon server in a background thread
    server_thread = threading.Thread(target=daemon.start_server)
    server_thread.daemon = True
    server_thread.start()

    # Wait for socket to appear
    deadline = time.time() + 5.0
    while not sock_path.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert sock_path.exists(), "Socket was not created by daemon"

    # Test 1: ping
    res = send_to_daemon({"action": "ping"})
    assert res == {"status": "pong"}

    # Test 2: toggle (start)
    res = send_to_daemon({"action": "toggle"})
    assert res == {"status": "started"}
    mock_recorder.start.assert_called_once()

    # Test 3: toggle (stop)
    with patch.object(daemon, "process_audio", return_value={"status": "ok", "cleaned": "hello"}):
        res = send_to_daemon({"action": "toggle"})
        assert res == {"status": "stopped"}

    # Test 4: process audio
    with patch.object(daemon, "process_audio", return_value={"status": "ok", "cleaned": "test audio"}):
        res = send_to_daemon({"action": "process", "audio_path": "/tmp/test.wav"})
        assert res == {"status": "ok", "cleaned": "test audio"}

    # Test 5: unknown action
    res = send_to_daemon({"action": "nonexistent"})
    assert "unknown action" in res.get("error", "")

    # Cleanup daemon server
    daemon.stop()
    assert not sock_path.exists()


@patch("voice_flow.daemon.Transcriber")
@patch("voice_flow.daemon.TextCleaner")
@patch("voice_flow.daemon.TextInjector")
@patch("voice_flow.daemon.AudioRecorder")
@patch("voice_flow.daemon.GlobalHotkeyListener")
def test_daemon_signal_handling_and_lifecycle(
    mock_hotkey_cls,
    mock_recorder_cls,
    mock_injector_cls,
    mock_cleaner_cls,
    mock_transcriber_cls,
    tmp_path,
    monkeypatch,
):
    from voice_flow.daemon import VoiceFlowDaemon

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    sock_path = get_socket_path()

    mock_hotkey = MagicMock()
    mock_hotkey_cls.return_value = mock_hotkey

    config = {
        "stt": {"device": "cpu", "model_size": "tiny"},
        "cleaner": {"enabled": False},
        "ui": {"restore_clipboard": False},
        "audio": {"temp_file": "auto"},
        "hotkey": {"enabled": True},
    }

    daemon = VoiceFlowDaemon(config)

    # Create dummy socket file to test that shutdown unlinks it
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    sock_path.touch()
    assert sock_path.exists()

    # Register signals in main thread
    registered = daemon.register_signal_handlers()
    assert registered is True

    # Verify SIGTERM handler is set to daemon._handle_signal
    current_handler = signal.getsignal(signal.SIGTERM)
    assert current_handler == daemon._handle_signal

    # Verify SIGINT handler is set to daemon._handle_signal
    current_int_handler = signal.getsignal(signal.SIGINT)
    assert current_int_handler == daemon._handle_signal

    # Invoking signal handler should unlink socket, stop hotkey listener, and exit
    with pytest.raises(SystemExit) as exc_info:
        daemon._handle_signal(signal.SIGTERM, None)

    assert exc_info.value.code == 0
    daemon.hotkey_listener.stop.assert_called()
    assert not sock_path.exists()
