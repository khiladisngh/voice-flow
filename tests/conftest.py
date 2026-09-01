import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is at the head of sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))


@pytest.fixture(autouse=True)
def isolate_desktop_session():
    """Keep the entire suite off the developer's live Wayland session.

    The three seams below are the only paths from this codebase to real
    hardware: /dev/uinput (which synthesizes keystrokes into whatever window
    has focus) and wl-copy/wl-paste (which overwrite the user's clipboard).
    Neutralising them here rather than per-test means a future test cannot
    reach the real session by forgetting to mock.

    Each UInput() call returns a *distinct* mock so tests can still assert
    device identity and re-initialisation. Individual tests may layer their own
    patches over these; nested patching restores cleanly.
    """
    with (
        patch("voice_flow.injector.evdev.UInput", side_effect=lambda *a, **kw: MagicMock()),
        patch("voice_flow.injector.TextInjector._set_clipboard"),
        patch("voice_flow.injector.TextInjector._get_current_clipboard", return_value=None),
    ):
        yield


@pytest.fixture(autouse=True)
def isolate_runtime_dir(tmp_path_factory, monkeypatch):
    """Point $XDG_RUNTIME_DIR at a temp directory for every test.

    voice_flow.paths derives the audio, PID, and socket paths from
    $XDG_RUNTIME_DIR at call time, and VoiceFlowDaemon.stop() unlinks the socket
    it resolves. Without this, a test that constructs or stops a daemon deletes
    the *live* daemon's socket, leaving a process that still handles hotkeys but
    can never answer `voice-flow status` again. That happened during
    development, so the isolation is enforced suite-wide rather than per-test.

    Tests that need their own runtime dir still monkeypatch XDG_RUNTIME_DIR
    themselves; a later monkeypatch simply overrides this one.
    """
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path_factory.mktemp("xdg")))
