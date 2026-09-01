import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

PID_FILE = Path("/dev/shm/voice_flow_record.pid")
DEFAULT_AUDIO_PATH = "/dev/shm/voice_flow_record.wav"

class AudioRecorder:
    def __init__(
        self,
        audio_path: str = DEFAULT_AUDIO_PATH,
        sample_rate: int = 16000,
        channels: int = 1,
        sound_feedback: bool = True,
        notifications: bool = True,
    ):
        self.audio_path = audio_path
        self.sample_rate = sample_rate
        self.channels = channels
        self.sound_feedback = sound_feedback
        self.notifications = notifications

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
        if not PID_FILE.exists():
            return False
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            if PID_FILE.exists():
                PID_FILE.unlink(missing_ok=True)
            return False

    def start(self) -> bool:
        if self.is_recording():
            return False

        if os.path.exists(self.audio_path):
            try:
                os.unlink(self.audio_path)
            except Exception:
                pass

        proc = subprocess.Popen(
            [
                "pw-record",
                "--channels", str(self.channels),
                "--rate", str(self.sample_rate),
                self.audio_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        PID_FILE.write_text(str(proc.pid))
        self.play_sound("audio-volume-change")
        self.notify("🎙️ Voice Flow", "Listening...", expire_ms=10000)
        return True

    def stop(self) -> Optional[str]:
        if not PID_FILE.exists():
            return None

        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGINT)
        except Exception:
            pass

        PID_FILE.unlink(missing_ok=True)

        # Wait briefly for pw-record to close wav header cleanly
        for _ in range(20):
            if os.path.exists(self.audio_path) and os.path.getsize(self.audio_path) > 44:
                break
            time.sleep(0.02)

        self.play_sound("message-new-instant")
        self.notify("⚡ Voice Flow", "Processing speech...", expire_ms=2000)
        return self.audio_path if os.path.exists(self.audio_path) else None
