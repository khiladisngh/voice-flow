import os
from pathlib import Path


def get_runtime_dir() -> Path:
    """
    Resolve and create the secure runtime directory for voice-flow.
    Prefers $XDG_RUNTIME_DIR, falls back to /run/user/<uid>.
    Ensures mode 0700 (owner rwx only).
    """
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base:
        base = f"/run/user/{os.getuid()}"
    path = Path(base) / "voice-flow"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def get_audio_path(session_id: str = "current") -> Path:
    """Return the path to a session's recorded audio wav file."""
    return get_runtime_dir() / f"record_{session_id}.wav"


def get_pid_file() -> Path:
    """Return the path to the recorder PID file."""
    return get_runtime_dir() / "recorder.pid"


def get_socket_path() -> Path:
    """Return the path to the daemon Unix domain socket."""
    return get_runtime_dir() / "daemon.sock"
