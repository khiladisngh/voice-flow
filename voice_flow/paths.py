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


def get_config_path() -> Path | None:
    """Resolve the active config file, or None if there is no config anywhere.

    Search order, first match wins:

    1. ``$VOICE_FLOW_CONFIG`` — explicit override.
    2. ``${XDG_CONFIG_HOME:-~/.config}/voice-flow/config.json`` — where a user
       is meant to keep their settings, and where the Homebrew
       ``voice-flow-setup`` helper writes the default template.
    3. The ``config.json`` beside the installed package — the source-checkout
       layout.

    The user location must come first. A packaged install (Homebrew, a wheel)
    puts the package under a read-only prefix that is replaced on upgrade, so
    editing the packaged copy either fails or is silently discarded.
    """
    override = os.environ.get("VOICE_FLOW_CONFIG")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None

    xdg = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    user_config = config_home / "voice-flow" / "config.json"
    if user_config.is_file():
        return user_config

    bundled = Path(__file__).resolve().parent.parent / "config.json"
    if bundled.is_file():
        return bundled

    return None
