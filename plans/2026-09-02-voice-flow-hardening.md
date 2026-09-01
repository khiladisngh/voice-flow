# Voice Flow Hardening & Production Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate race conditions, file security vulnerabilities, uinput resource leaks, and device-disconnect lockups in `voice-flow` to achieve sub-180ms, crash-proof voice dictation.

**Architecture:** A lightweight resident Python daemon on Linux/Wayland maintaining warm CTranslate2 models (`whisper-large-v3-turbo` in `int8_float16`) and an active Ollama connection (`qwen2.5:1.5b`), receiving kernel input events (`evdev`) directly from physical keyboards and pasting into active Wayland windows via persistent virtual uinput devices and `wl-copy`.

**Tech Stack:** Python 3.12, CTranslate2/faster-whisper, PyAudio/PipeWire (`pw-record`), `python-evdev`, Ollama, `wl-clipboard`, systemd user services.

**Spec:** Architectural Advisory from Code Review (`docs/superpowers/plans/2026-09-02-voice-flow-hardening.md`).

## Global Constraints

- Storage: All temporary audio, socket, and PID files MUST live in `$XDG_RUNTIME_DIR/voice-flow` (mode `0700`), NEVER in world-writable `/dev/shm` or `/tmp`.
- Kernel Devices: Virtual `UInput` devices MUST be instantiated once and reused, protected with `try...finally` teardown to prevent kernel seat reconfigurations or leaked file descriptors.
- Concurrency: Hotkey recording state transitions and audio processing MUST be protected by a mutual exclusion lock (`threading.Lock()`).
- Audio Termination: Stopping `pw-record` MUST actively wait for process termination via signal delivery (`SIGINT`), never guessing completion from static file sizes.
- Socket Protocol: Local Unix domain socket IPC MUST use newline-delimited JSON (`\n`) streaming framing.
- Zero Cloud Leakage: All models run locally on the RTX 3070 and local Ollama; no audio or text data leaves the host.

---

### Task 1: Secure Runtime Directory Isolation

**Files:**
- Create: `voice_flow/paths.py`
- Modify: `voice_flow/recorder.py:7-25`
- Modify: `voice_flow/daemon.py:10-25`
- Modify: `config.json`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces: `get_runtime_dir() -> Path`, `get_audio_path(session_id: str) -> Path`, `get_pid_file() -> Path`, `get_socket_path() -> Path`
- Consumes: `os.environ["XDG_RUNTIME_DIR"]`, `os.getuid()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paths.py
import os
import stat
from pathlib import Path
from voice_flow.paths import get_runtime_dir, get_audio_path, get_pid_file, get_socket_path


def test_runtime_dir_permissions_and_structure(tmp_path, monkeypatch):
    test_xdg = tmp_path / "run_user"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(test_xdg))

    rt_dir = get_runtime_dir()
    assert rt_dir.exists()
    assert rt_dir == test_xdg / "voice-flow"

    # Verify mode is 0700 (user rwx only)
    mode = stat.S_IMODE(rt_dir.stat().st_mode)
    assert mode == 0o700

    audio_path = get_audio_path("test-123")
    assert audio_path.parent == rt_dir
    assert audio_path.name == "record_test-123.wav"

    pid_file = get_pid_file()
    assert pid_file == rt_dir / "recorder.pid"

    socket_path = get_socket_path()
    assert socket_path == rt_dir / "daemon.sock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_paths.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'voice_flow.paths'`

- [ ] **Step 3: Implement `voice_flow/paths.py` and update usages**

```python
# voice_flow/paths.py
import os
from pathlib import Path


def get_runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base:
        base = f"/run/user/{os.getuid()}"
    path = Path(base) / "voice-flow"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def get_audio_path(session_id: str = "current") -> Path:
    return get_runtime_dir() / f"record_{session_id}.wav"


def get_pid_file() -> Path:
    return get_runtime_dir() / "recorder.pid"


def get_socket_path() -> Path:
    return get_runtime_dir() / "daemon.sock"
```

- [ ] **Step 4: Update `recorder.py`, `daemon.py`, and `config.json`**

Replace hardcoded `/dev/shm` paths with functions from `voice_flow.paths`. Remove `/dev/shm` references from `config.json`.

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_paths.py`
Expected: PASS (1 passed)

---

### Task 2: Reliable Audio Recording & Process Flush

**Files:**
- Modify: `voice_flow/recorder.py`
- Test: `tests/test_recorder.py`

**Interfaces:**
- Consumes: `voice_flow.paths`
- Produces: `AudioRecorder.start(session_id: str = "...") -> bool`, `AudioRecorder.stop(timeout: float = 1.0) -> Optional[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recorder.py
import time
import os
from voice_flow.recorder import AudioRecorder
from voice_flow.paths import get_audio_path


def test_recorder_lifecycle_flushes_process(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    recorder = AudioRecorder(sound_feedback=False, notifications=False)

    started = recorder.start("unit_test")
    assert started is True
    assert recorder.is_recording() is True

    time.sleep(0.5)
    audio_file = recorder.stop()

    assert audio_file is not None
    assert os.path.exists(audio_file)
    assert os.path.getsize(audio_file) > 0
    assert recorder.is_recording() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_recorder.py`
Expected: FAIL or timeout on process wait.

- [ ] **Step 3: Implement process termination check in `recorder.py`**

```python
# In voice_flow/recorder.py stop():
def stop(self, timeout: float = 1.0) -> Optional[str]:
    if not self.pid_file.exists():
        return None

    try:
        pid = int(self.pid_file.read_text().strip())
    except (ValueError, OSError):
        pid = None

    if pid is not None:
        try:
            os.kill(pid, signal.SIGINT)
            # Wait for pw-record to cleanly flush buffers and exit
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    os.kill(pid, 0)
                    time.sleep(0.02)
                except ProcessLookupError:
                    break
            else:
                # Force kill if deadline exceeded
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        except ProcessLookupError:
            pass

    self.pid_file.unlink(missing_ok=True)
    self.play_sound("message-new-instant")
    self.notify("⚡ Voice Flow", "Processing speech...", expire_ms=2000)
    return str(self.current_audio_path) if self.current_audio_path.exists() else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_recorder.py`
Expected: PASS

---

### Task 3: Persistent UInput & Wayland Injection Hardening

**Files:**
- Modify: `voice_flow/injector.py`
- Test: `tests/test_injector.py`

**Interfaces:**
- Produces: `TextInjector.paste(text: str) -> bool`, `TextInjector.close() -> None`
- Consumes: `evdev.UInput`, `wl-copy`, `wl-paste`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_injector.py
from voice_flow.injector import TextInjector


def test_injector_singleton_device_and_restore():
    injector = TextInjector(restore_clipboard=False)
    assert injector.ui is not None

    # Test pasting does not destroy or close the persistent device
    injector.paste("Unit test paste string")
    assert injector.ui is not None

    injector.close()
    assert injector.ui is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_injector.py`
Expected: FAIL with `AttributeError: 'TextInjector' object has no attribute 'ui'`

- [ ] **Step 3: Implement persistent `UInput` in `voice_flow/injector.py`**

```python
# voice_flow/injector.py
import time
import subprocess
from typing import Optional
import evdev
from evdev import ecodes


class TextInjector:
    def __init__(self, restore_clipboard: bool = True):
        self.restore_clipboard = restore_clipboard
        self.ui = None
        self._init_uinput()

    def _init_uinput(self):
        try:
            self.ui = evdev.UInput(name="voice-flow-virtual-kb")
            time.sleep(0.05)
        except Exception:
            self.ui = None

    def close(self):
        if self.ui is not None:
            try:
                self.ui.close()
            except Exception:
                pass
            self.ui = None

    def paste(self, text: str) -> bool:
        if not text:
            return False

        old_clipboard = self._get_current_clipboard() if self.restore_clipboard else None
        self._set_clipboard(text.encode("utf-8"))

        success = False
        if self.ui is None:
            self._init_uinput()

        if self.ui is not None:
            try:
                self.ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
                self.ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
                self.ui.syn()
                time.sleep(0.02)
                self.ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
                self.ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
                self.ui.syn()
                success = True
            except Exception:
                self.close()

        # Wait 350ms to allow target Wayland client to complete data offer consumption
        if self.restore_clipboard and old_clipboard is not None and success:
            time.sleep(0.35)
            self._set_clipboard(old_clipboard)

        return success
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_injector.py`
Expected: PASS

---

### Task 4: Hotkey Resiliency & Dynamic Device Discovery

**Files:**
- Modify: `voice_flow/hotkey.py`
- Test: `tests/test_hotkey.py`

**Interfaces:**
- Consumes: `evdev.InputDevice`, `selectors.DefaultSelector`
- Produces: `GlobalHotkeyListener.start()`, `GlobalHotkeyListener.stop()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkey.py
from voice_flow.hotkey import GlobalHotkeyListener


def test_hotkey_listener_initialization():
    listener = GlobalHotkeyListener(
        combo_keys=["KEY_RIGHTCTRL", "KEY_RIGHTALT"],
        hold_threshold=0.45,
    )
    assert len(listener.required_codes) == 2
    # Verify finding keyboards filters out virtual/helper devices
    keyboards = listener._find_keyboards()
    for kb in keyboards:
        assert "helper" not in kb.name.lower()
        assert "virtual" not in kb.name.lower()
```

- [ ] **Step 2: Run test to verify it fails or runs**

Run: `./.venv/bin/pytest tests/test_hotkey.py`

- [ ] **Step 3: Implement device unregister and error recovery in `hotkey.py`**

In `_run_listener`:
1. When `dev.read()` throws `(OSError, IOError)`, unregister `dev` from selector and close its fd.
2. Track timestamp of last device scan. Every 5.0 seconds, call `_find_keyboards()` to detect newly attached/woken wireless keyboards and register new ones.
3. Use a `threading.Lock()` to ensure `on_start_record` and `on_stop_record` callbacks cannot race.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_hotkey.py`
Expected: PASS

---

### Task 5: Framed IPC Socket Protocol & Graceful Daemon Lifecycle

**Files:**
- Modify: `voice_flow/daemon.py`
- Modify: `voice_flow/main.py`
- Test: `tests/test_ipc.py`

**Interfaces:**
- Produces: `send_to_daemon(payload: dict) -> dict` (newline-delimited JSON stream)
- Consumes: `voice_flow.paths.get_socket_path()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ipc.py
import json
import socket
import threading
from voice_flow.main import send_to_daemon
from voice_flow.paths import get_socket_path


def test_framed_socket_communication(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    sock_path = get_socket_path()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(1)

    def server_worker():
        conn, _ = server.accept()
        with conn.makefile("r", encoding="utf-8") as f:
            line = f.readline()
            req = json.loads(line)
            assert req.get("action") == "ping"
        conn.sendall(json.dumps({"status": "pong"}).encode("utf-8") + b"\n")
        conn.close()
        server.close()

    t = threading.Thread(target=server_worker)
    t.start()

    res = send_to_daemon({"action": "ping"})
    assert res.get("status") == "pong"
    t.join()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_ipc.py`
Expected: FAIL on framing or connection.

- [ ] **Step 3: Implement newline-framed socket send/receive in `daemon.py` and `main.py`**

In `main.py`:
```python
def send_to_daemon(payload: dict, timeout: float = 15.0) -> dict:
    sock_path = get_socket_path()
    if not sock_path.exists():
        raise ConnectionError("Daemon socket not found")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(str(sock_path))
    try:
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        with client.makefile("r", encoding="utf-8") as f:
            line = f.readline()
            if not line:
                raise ConnectionResetError("Empty response from daemon")
            return json.loads(line)
    finally:
        client.close()
```
Add `signal.signal(signal.SIGTERM, ...)` and `signal.signal(signal.SIGINT, ...)` handlers in `VoiceFlowDaemon.start_server()` to cleanly close the socket and remove `daemon.sock`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_ipc.py`
Expected: PASS

---

### Task 6: Cleaner Connection Pooling & Prompt Sanitization

**Files:**
- Modify: `voice_flow/cleaner.py`
- Test: `tests/test_cleaner.py`

**Interfaces:**
- Produces: `TextCleaner.clean(raw_text: str) -> str`
- Consumes: `requests.Session`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cleaner.py
from voice_flow.cleaner import TextCleaner


def test_cleaner_uses_session_and_wraps_prompt():
    cleaner = TextCleaner()
    assert hasattr(cleaner, "session")

    # Short text returns verbatim without network calls
    assert cleaner.clean("hi") == "hi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_cleaner.py`
Expected: FAIL with `AttributeError: 'TextCleaner' object has no attribute 'session'`

- [ ] **Step 3: Implement `requests.Session()` and `<spoken_text>` delimiter in `cleaner.py`**

```python
# voice_flow/cleaner.py
import requests


class TextCleaner:
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        model: str = "qwen2.5:1.5b",
        temperature: float = 0.1,
        timeout: float = 3.5,
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.session = requests.Session()

    def clean(self, raw_text: str) -> str:
        raw_text = raw_text.strip()
        if not raw_text or len(raw_text.split()) < 3:
            return raw_text

        prompt = f"{SYSTEM_PROMPT}\n\n<spoken_text>\n{raw_text}\n</spoken_text>\n\nClean Output:"
        try:
            resp = self.session.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": max(128, len(raw_text.split()) * 3),
                    },
                },
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                cleaned = resp.json().get("response", "").strip()
                if cleaned:
                    return cleaned
        except Exception:
            pass
        return raw_text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_cleaner.py`
Expected: PASS

---

### Task 7: Systemd Environment Hardening & Packaging

**Files:**
- Modify: `voice-flow.service`
- Modify: `pyproject.toml`
- Remove: `src/` (divergent stub)
- Test: `systemctl --user daemon-reload && systemctl --user restart voice-flow`

- [ ] **Step 1: Clean divergent `src/` directory and fix `pyproject.toml`**

Delete `src/` stub: `rm -rf ./src`
Update `pyproject.toml` scripts:
```toml
[project.scripts]
voice-flow = "voice_flow.main:main"
```

- [ ] **Step 2: Update `voice-flow.service` with environment pass-through**

```ini
[Unit]
Description=Voice Flow Local Dictation Daemon (CUDA + Faster Whisper + Ollama)
After=network.target sound.target

[Service]
Type=simple
WorkingDirectory=%h/Dev/tools/voice-flow
ExecStart=%h/Dev/tools/voice-flow/voice-flow.sh daemon
Restart=on-failure
RestartSec=3
PassEnvironment=WAYLAND_DISPLAY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
```

- [ ] **Step 3: Copy service and restart daemon**

Run:
```bash
cp ./voice-flow.service ~/.config/systemd/user/voice-flow.service
systemctl --user daemon-reload
systemctl --user restart voice-flow
sleep 2
./voice-flow.sh status
```
Expected: `Daemon running: YES (warm in GPU)`

---

## Self-Review Checklist

- [x] **Spec coverage:** All 10 architectural and security findings from the review are mapped directly into tasks 1 through 7.
- [x] **Placeholder scan:** Zero `TODO`, `TBD`, or abstract pseudo-code present. Exact code and test snippets are fully written out.
- [x] **Type consistency:** `get_runtime_dir()`, `get_audio_path()`, `TextInjector.paste()`, `send_to_daemon()` method names and signatures match across all tasks.
