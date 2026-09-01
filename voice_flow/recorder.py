import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional
from voice_flow.paths import get_audio_path, get_pid_file

PID_FILE = get_pid_file()
DEFAULT_AUDIO_PATH = str(get_audio_path())

class AudioRecorder:
    def __init__(
        self,
        audio_path: Optional[str] = None,
        sample_rate: int = 16000,
        channels: int = 1,
        sound_feedback: bool = True,
        notifications: bool = True,
    ):
        self._custom_audio_path = audio_path is not None and audio_path != "auto"
        if self._custom_audio_path:
            self.audio_path = str(audio_path)
            self.current_audio_path: Path = Path(self.audio_path)
        else:
            self.current_audio_path = get_audio_path()
            self.audio_path = str(self.current_audio_path)
        self.sample_rate = sample_rate
        self.channels = channels
        self.sound_feedback = sound_feedback
        self.notifications = notifications
    @property
    def pid_file(self) -> Path:
        return get_pid_file()
    def notify(self, title: str, message: str, expire_ms: int = 1500):
        if not self.notifications:
            return
        try:
            subprocess.Popen(
                ["notify-send", "-a", "Voice Flow", "-t", str(expire_ms), "-h", "int:transient:1", title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def play_sound(self, sound_name: str = "audio-volume-change"):
        if not self.sound_feedback:
            return
        # Look for standard freedesktop system sound
        sound_paths = [
            f"/usr/share/sounds/freedesktop/stereo/{sound_name}.oga",
            "/usr/share/sounds/freedesktop/stereo/bell.oga",
        ]
        for p in sound_paths:
            if os.path.exists(p):
                try:
                    subprocess.Popen(["pw-play", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except Exception:
                    pass

    def is_recording(self) -> bool:
        if not self.pid_file.exists():
            return False
        try:
            pid = int(self.pid_file.read_text().strip())
            try:
                wpid, _ = os.waitpid(pid, os.WNOHANG)
                if wpid != 0:
                    self.pid_file.unlink(missing_ok=True)
                    return False
            except ChildProcessError:
                pass
            os.kill(pid, 0)
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            if self.pid_file.exists():
                self.pid_file.unlink(missing_ok=True)
            return False
    def start(self, session_id: str = "current") -> bool:
        if self.is_recording():
            return False

        if self._custom_audio_path and session_id == "current":
            self.current_audio_path = Path(self.audio_path)
        else:
            self.current_audio_path = get_audio_path(session_id)
            self.audio_path = str(self.current_audio_path)

        self.current_audio_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        if self.current_audio_path.exists():
            try:
                self.current_audio_path.unlink()
            except Exception:
                pass

        env = os.environ.copy()
        if "PIPEWIRE_RUNTIME_DIR" not in env:
            uid = os.getuid()
            default_pw_socket = Path(f"/run/user/{uid}/pipewire-0")
            if default_pw_socket.exists():
                env["PIPEWIRE_RUNTIME_DIR"] = f"/run/user/{uid}"

        proc = subprocess.Popen(
            [
                "pw-record",
                "--channels", str(self.channels),
                "--rate", str(self.sample_rate),
                str(self.current_audio_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        self.pid_file.write_text(str(proc.pid))
        self.play_sound("audio-volume-change")
        self.notify("🎙️ Voice Flow", "Listening...", expire_ms=10000)
        return True
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
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        wpid, _ = os.waitpid(pid, os.WNOHANG)
                        if wpid != 0:
                            break
                    except ChildProcessError:
                        pass

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
                    kill_deadline = time.time() + 0.5
                    while time.time() < kill_deadline:
                        try:
                            wpid, _ = os.waitpid(pid, os.WNOHANG)
                            if wpid != 0:
                                break
                        except ChildProcessError:
                            pass
                        try:
                            os.kill(pid, 0)
                            time.sleep(0.01)
                        except ProcessLookupError:
                            break
            except ProcessLookupError:
                pass

        self.pid_file.unlink(missing_ok=True)
        self.play_sound("message-new-instant")
        self.notify("⚡ Voice Flow", "Processing speech...", expire_ms=2000)

        audio_path = Path(self.current_audio_path) if self.current_audio_path else None
        if audio_path and audio_path.exists() and audio_path.stat().st_size > 0:
            return str(audio_path)
        return None
