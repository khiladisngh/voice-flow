import os
import subprocess
import time
from pathlib import Path

import pytest

from voice_flow.paths import get_audio_path, get_pid_file
from voice_flow.recorder import AudioRecorder


@pytest.mark.pipewire
def test_recorder_lifecycle_flushes_process(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recorder = AudioRecorder(sound_feedback=False, notifications=False)

    started = recorder.start("unit_test")
    assert started is True
    assert recorder.is_recording() is True

    time.sleep(0.3)
    audio_file = recorder.stop()

    assert audio_file is not None
    assert os.path.exists(audio_file)
    assert os.path.getsize(audio_file) > 0
    assert recorder.is_recording() is False
    assert "record_unit_test.wav" in audio_file


@pytest.mark.pipewire
def test_recorder_start_already_recording(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recorder = AudioRecorder(sound_feedback=False, notifications=False)

    assert recorder.start("first_session") is True
    assert recorder.start("second_session") is False

    time.sleep(0.3)
    audio_file = recorder.stop()
    assert "record_first_session.wav" in audio_file


def test_recorder_stop_not_recording(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recorder = AudioRecorder(sound_feedback=False, notifications=False)
    assert recorder.stop() is None


def test_recorder_stop_empty_audio_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recorder = AudioRecorder(sound_feedback=False, notifications=False)

    # Spawn dummy short-lived process
    proc = subprocess.Popen(["sleep", "0.05"])
    get_pid_file().write_text(str(proc.pid))
    # Create empty audio file (0 bytes)
    audio_path = get_audio_path("empty_test")
    audio_path.touch()
    recorder.current_audio_path = audio_path

    res = recorder.stop(timeout=1.0)
    assert res is None
    assert not get_pid_file().exists()


def test_recorder_stop_timeout_force_kills(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recorder = AudioRecorder(sound_feedback=False, notifications=False)

    # Spawn process that traps SIGINT and ignores it
    proc = subprocess.Popen(
        ["python3", "-c", "import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN); time.sleep(10)"]
    )
    get_pid_file().write_text(str(proc.pid))
    audio_path = get_audio_path("sigkill_test")
    audio_path.write_bytes(b"RIFF....WAVEfmt ....data....")
    recorder.current_audio_path = audio_path

    try:
        res = recorder.stop(timeout=0.1)
        assert res == str(audio_path)
        # Verify process was terminated by SIGKILL
        proc.wait(timeout=1.0)
        assert not get_pid_file().exists()
    finally:
        try:
            proc.kill()
        except OSError:
            pass


@pytest.mark.pipewire
def test_recorder_session_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recorder = AudioRecorder(sound_feedback=False, notifications=False)

    recorder.start("session_alpha")
    assert "record_session_alpha.wav" in str(recorder.current_audio_path)
    recorder.stop()

    recorder.start("session_beta")
    assert "record_session_beta.wav" in str(recorder.current_audio_path)
    recorder.stop()


def test_recorder_stop_corrupted_pid_file(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recorder = AudioRecorder(sound_feedback=False, notifications=False)

    get_pid_file().write_text("not-a-pid")
    res = recorder.stop()
    assert res is None
    assert not get_pid_file().exists()


def test_recorder_stop_already_dead_process(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recorder = AudioRecorder(sound_feedback=False, notifications=False)

    # Write a PID that doesn't exist (e.g. 999999)
    get_pid_file().write_text("999999")
    res = recorder.stop()
    assert res is None
    assert not get_pid_file().exists()


@pytest.mark.pipewire
def test_recorder_custom_audio_path_handling(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    custom_path = str(tmp_path / "custom_recording.wav")
    recorder = AudioRecorder(audio_path=custom_path, sound_feedback=False, notifications=False)

    assert recorder.start("current") is True
    assert recorder.current_audio_path == Path(custom_path)
    time.sleep(0.3)
    res = recorder.stop()
    assert res == custom_path
    assert os.path.exists(custom_path)
