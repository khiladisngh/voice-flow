import errno
import json
import signal
import socket
import sys
import time

from voice_flow.cleaner import TextCleaner
from voice_flow.hotkey import GlobalHotkeyListener
from voice_flow.injector import TextInjector
from voice_flow.paths import get_runtime_dir, get_socket_path
from voice_flow.recorder import AudioRecorder
from voice_flow.transcriber import Transcriber


class VoiceFlowDaemon:
    def __init__(self, config: dict):
        self.config = config
        self._shutting_down = False
        # Holds the path this daemon actually bound so shutdown cannot unlink another process's socket.
        self.socket_path = None
        stt_cfg = config.get("stt", {})
        cleaner_cfg = config.get("cleaner", {})
        ui_cfg = config.get("ui", {})
        audio_cfg = config.get("audio", {})
        hotkey_cfg = config.get("hotkey", {})

        print(
            f"[Daemon] Initializing Transcriber on {stt_cfg.get('device', 'cuda')} ({stt_cfg.get('model_size', 'large-v3-turbo')})..."
        )
        self.transcriber = Transcriber(
            model_size=stt_cfg.get("model_size", "large-v3-turbo"),
            device=stt_cfg.get("device", "cuda"),
            compute_type=stt_cfg.get("compute_type", "int8_float16"),
            language=stt_cfg.get("language"),
        )

        self.cleaner = None
        if cleaner_cfg.get("enabled", True):
            model = cleaner_cfg.get("model", "hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M")
            print(f"[Daemon] Connecting to Ollama cleaner ({model})...")
            self.cleaner = TextCleaner(
                ollama_url=cleaner_cfg.get("ollama_url", "http://localhost:11434/api/generate"),
                model=model,
                temperature=cleaner_cfg.get("temperature", 0.1),
                timeout=cleaner_cfg.get("timeout_sec", 15.0),
                keep_alive=cleaner_cfg.get("keep_alive", -1),
                options=cleaner_cfg.get("options", {}),
            )
            # Pay the model-load cost now, not on the user's first dictation.
            if self.cleaner.warm_up():
                print("[Daemon] Cleaner model warm and pinned in VRAM")
            else:
                print(
                    "[Daemon] Cleaner model unavailable; cleanup will fall back to raw transcripts "
                    "until the model is available"
                )

        self.injector = TextInjector(restore_clipboard=ui_cfg.get("restore_clipboard", True))
        temp_file = audio_cfg.get("temp_file", "auto")
        self.recorder = AudioRecorder(
            audio_path=None if temp_file == "auto" else temp_file,
            sample_rate=audio_cfg.get("sample_rate", 16000),
            channels=audio_cfg.get("channels", 1),
            sound_feedback=ui_cfg.get("sound_feedback", True),
            notifications=ui_cfg.get("notifications", True),
        )

        # Global Hotkey Listener (direct evdev kernel input)
        self.hotkey_listener = None
        if hotkey_cfg.get("enabled", True):
            combo = hotkey_cfg.get("combo", ["KEY_RIGHTCTRL", "KEY_RIGHTALT"])
            hold_sec = hotkey_cfg.get("hold_threshold_sec", 0.45)
            self.hotkey_listener = GlobalHotkeyListener(
                combo_keys=combo,
                hold_threshold=hold_sec,
                on_start_record=self.on_hotkey_start,
                on_stop_record=self.on_hotkey_stop,
            )
            self.hotkey_listener.start()

        print("[Daemon] Voice Flow Daemon is warm and ready!")

    def on_hotkey_start(self):
        print("[Daemon] Hotkey triggered: START recording")
        self.recorder.start()

    def on_hotkey_stop(self):
        print("[Daemon] Hotkey triggered: STOP recording & process")
        audio_file = self.recorder.stop()
        if audio_file:
            result = self.process_audio(audio_file)
            pasted_str = "Pasted" if result.get("pasted") else "Paste FAILED (check /dev/uinput)"
            print(
                f'[Daemon] Transcribed & {pasted_str}: "{result.get("cleaned")}" ({result.get("total_ms")}ms)'
            )

    def process_audio(self, audio_path: str) -> dict:
        t0 = time.time()
        raw_text, lang, duration = self.transcriber.transcribe(audio_path)
        t_stt = time.time() - t0

        final_text = raw_text
        t_clean = 0.0
        if self.cleaner and raw_text:
            t1 = time.time()
            final_text = self.cleaner.clean(raw_text, language=lang)
            t_clean = time.time() - t1

        # Paste into active window
        pasted = False
        if final_text:
            pasted = bool(self.injector.paste(final_text))

        total_ms = (time.time() - t0) * 1000
        return {
            "status": "ok",
            "raw": raw_text,
            "cleaned": final_text,
            "language": lang,
            "duration": duration,
            "pasted": pasted,
            "stt_ms": round(t_stt * 1000, 1),
            "clean_ms": round(t_clean * 1000, 1),
            "total_ms": round(total_ms, 1),
        }

    def _handle_signal(self, signum, frame):
        print(f"[Daemon] Received signal {signum}, shutting down gracefully...")
        self.stop()
        sys.exit(0)

    def register_signal_handlers(self):
        try:
            self._prev_sigterm = signal.signal(signal.SIGTERM, self._handle_signal)
            self._prev_sigint = signal.signal(signal.SIGINT, self._handle_signal)
            return True
        except (ValueError, AttributeError):
            return False

    def stop(self):
        """Stop the daemon server and cleanup resources."""
        self._shutting_down = True
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        if self.socket_path and self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception:
                pass
        if getattr(self, "server", None):
            try:
                self.server.close()
            except Exception:
                pass

    def start_server(self):
        get_runtime_dir()  # side effect: creates $XDG_RUNTIME_DIR/voice-flow at mode 0700
        self.socket_path = get_socket_path()
        if self.socket_path.exists():
            self.socket_path.unlink()

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.socket_path))
        self.server.listen(5)
        print(f"[Daemon] Listening on Unix socket: {self.socket_path}")

        self.register_signal_handlers()
        try:
            while not self._shutting_down:
                try:
                    conn, _ = self.server.accept()
                except OSError as exc:
                    # A closed listening socket during shutdown is expected.
                    # Anything else (ECONNABORTED, EINTR, EMFILE) is transient:
                    # log it and keep serving rather than killing IPC for the
                    # lifetime of the daemon.
                    if self._shutting_down or exc.errno in (errno.EBADF, errno.EINVAL):
                        break
                    print(
                        f"[Daemon] accept() failed ({errno.errorcode.get(exc.errno, exc.errno)}); continuing"
                    )
                    continue
                try:
                    with conn.makefile("r", encoding="utf-8") as f:
                        line = f.readline()
                    if not line:
                        continue
                    req = json.loads(line)
                    action = req.get("action")

                    if action == "ping":
                        res = {"status": "pong"}
                    elif action == "process":
                        audio_path = req.get("audio_path")
                        res = self.process_audio(audio_path)
                    elif action == "toggle":
                        if self.recorder.is_recording():
                            self.on_hotkey_stop()
                            res = {"status": "stopped"}
                        else:
                            self.on_hotkey_start()
                            res = {"status": "started"}
                    else:
                        res = {"error": f"unknown action {action}"}

                    conn.sendall(json.dumps(res).encode("utf-8") + b"\n")
                except Exception as e:
                    try:
                        conn.sendall(json.dumps({"error": str(e)}).encode("utf-8") + b"\n")
                    except Exception:
                        pass
                finally:
                    conn.close()
        finally:
            self.stop()
            if getattr(self, "_prev_sigterm", None) is not None:
                try:
                    signal.signal(signal.SIGTERM, self._prev_sigterm)
                except (ValueError, AttributeError):
                    pass
            if getattr(self, "_prev_sigint", None) is not None:
                try:
                    signal.signal(signal.SIGINT, self._prev_sigint)
                except (ValueError, AttributeError):
                    pass
