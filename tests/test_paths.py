import sys
from pathlib import Path

# Ensure project root takes precedence over any installed stub
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import stat
from pathlib import Path

from voice_flow.paths import get_audio_path, get_config_path, get_pid_file, get_runtime_dir, get_socket_path


def test_runtime_dir_permissions_and_structure(tmp_path, monkeypatch):
    test_xdg = tmp_path / "run_user"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(test_xdg))

    rt_dir = get_runtime_dir()
    assert rt_dir.exists()
    assert rt_dir == test_xdg / "voice-flow"

    # Verify mode is 0700 (user rwx only)
    mode = stat.S_IMODE(rt_dir.stat().st_mode)
    assert mode == 0o700

    # Test custom session audio path
    audio_path = get_audio_path("test-123")
    assert audio_path.parent == rt_dir
    assert audio_path.name == "record_test-123.wav"

    # Test default session audio path
    default_audio = get_audio_path()
    assert default_audio.parent == rt_dir
    assert default_audio.name == "record_current.wav"

    pid_file = get_pid_file()
    assert pid_file == rt_dir / "recorder.pid"

    socket_path = get_socket_path()
    assert socket_path == rt_dir / "daemon.sock"


def test_runtime_dir_fallback_without_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(os, "getuid", lambda: 12345)

    # /run/user/12345 is not creatable in a test, so assert on the resolved path
    # while stubbing out the filesystem calls.
    from unittest.mock import patch

    with (
        patch("voice_flow.paths.Path.mkdir") as mock_mkdir,
        patch("voice_flow.paths.Path.chmod") as mock_chmod,
    ):
        rt_dir = get_runtime_dir()
        assert rt_dir == Path("/run/user/12345/voice-flow")
        mock_mkdir.assert_called_once_with(mode=0o700, parents=True, exist_ok=True)
        mock_chmod.assert_called_once_with(0o700)


def test_runtime_dir_enforces_0700_on_existing_dir(tmp_path, monkeypatch):
    test_xdg = tmp_path / "run_user"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(test_xdg))
    rt_dir = test_xdg / "voice-flow"
    rt_dir.mkdir(parents=True, mode=0o755)
    # Intentionally set mode to 0755
    rt_dir.chmod(0o755)
    assert stat.S_IMODE(rt_dir.stat().st_mode) == 0o755

    resolved = get_runtime_dir()
    assert resolved == rt_dir
    assert stat.S_IMODE(resolved.stat().st_mode) == 0o700


def test_recorder_uses_isolated_paths(tmp_path, monkeypatch):
    test_xdg = tmp_path / "run_user"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(test_xdg))
    from voice_flow.recorder import AudioRecorder

    rec = AudioRecorder(audio_path="auto")
    assert rec.audio_path == str(test_xdg / "voice-flow" / "record_current.wav")
    assert rec.pid_file == test_xdg / "voice-flow" / "recorder.pid"
    assert "/dev/shm" not in rec.audio_path
    assert "/dev/shm" not in str(rec.pid_file)

    rec_default = AudioRecorder()
    assert rec_default.audio_path == str(test_xdg / "voice-flow" / "record_current.wav")
    assert rec_default.pid_file == test_xdg / "voice-flow" / "recorder.pid"


def test_config_path_prefers_user_location_over_bundled(tmp_path, monkeypatch):
    """A packaged install must read the user's config, not the read-only copy."""
    monkeypatch.delenv("VOICE_FLOW_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    user_config = tmp_path / "voice-flow" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text('{"stt": {"model_size": "from-user-config"}}')

    assert get_config_path() == user_config


def test_config_path_env_override_wins(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit.json"
    explicit.write_text("{}")
    monkeypatch.setenv("VOICE_FLOW_CONFIG", str(explicit))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert get_config_path() == explicit


def test_config_path_missing_override_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_FLOW_CONFIG", str(tmp_path / "nope.json"))
    assert get_config_path() is None


def test_load_config_reads_user_location(tmp_path, monkeypatch):
    from voice_flow.main import load_config

    monkeypatch.delenv("VOICE_FLOW_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    user_config = tmp_path / "voice-flow" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text('{"cleaner": {"enabled": false}}')

    assert load_config() == {"cleaner": {"enabled": False}}


def test_load_config_tolerates_malformed_json(tmp_path, monkeypatch):
    from voice_flow.main import load_config

    monkeypatch.delenv("VOICE_FLOW_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    user_config = tmp_path / "voice-flow" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text("{ not valid json")

    assert load_config() == {}
