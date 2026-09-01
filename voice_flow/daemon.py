import os
import sys
import json
import time
import socket
from pathlib import Path
from voice_flow.transcriber import Transcriber
from voice_flow.cleaner import TextCleaner
from voice_flow.injector import TextInjector
from voice_flow.recorder import AudioRecorder
from voice_flow.hotkey import GlobalHotkeyListener
from voice_flow.paths import get_runtime_dir, get_socket_path

SOCKET_DIR = get_runtime_dir()
SOCKET_PATH = get_socket_path()
class VoiceFlowDaemon:
    def __init__(self, config: dict):
        self.config = config
        stt_cfg = config.get("stt", {})
        cleaner_cfg = config.get("cleaner", {})
        ui_cfg = config.get("ui", {})
        audio_cfg = config.get("audio", {})
        hotkey_cfg = config.get("hotkey", {})

        print(f"[Daemon] Initializing Transcriber on {stt_cfg.get('device', 'cuda')} ({stt_cfg.get('model_size', 'large-v3-turbo')})...")
        self.transcriber = Transcriber(
            model_size=stt_cfg.get("model_size", "large-v3-turbo"),
            device=stt_cfg.get("device", "cuda"),
            compute_type=stt_cfg.get("compute_type", "int8_float16"),
            language=stt_cfg.get("language"),
        )

        self.cleaner = None
        if cleaner_cfg.get("enabled", True):
            print(f"[Daemon] Connecting to Ollama cleaner ({cleaner_cfg.get('model', 'qwen2.5:1.5b')})...")
            self.cleaner = TextCleaner(
                ollama_url=cleaner_cfg.get("ollama_url", "http://localhost:11434/api/generate"),
                model=cleaner_cfg.get("model", "qwen2.5:1.5b"),
                temperature=cleaner_cfg.get("temperature", 0.1),
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
            print(f"[Daemon] Transcribed & Pasted: \"{result.get('cleaned')}\" ({result.get('total_ms')}ms)")

    def process_audio(self, audio_path: str) -> dict:
        t0 = time.time()
        raw_text, lang, duration = self.transcriber.transcribe(audio_path)
        t_stt = time.time() - t0

        final_text = raw_text
        t_clean = 0.0
        if self.cleaner and raw_text:
            t1 = time.time()
            final_text = self.cleaner.clean(raw_text)
            t_clean = time.time() - t1

        # Paste into active window
        if final_text:
            self.injector.paste(final_text)

        total_ms = (time.time() - t0) * 1000
        return {
            "status": "ok",
            "raw": raw_text,
            "cleaned": final_text,
            "language": lang,
            "duration": duration,
            "stt_ms": round(t_stt * 1000, 1),
            "clean_ms": round(t_clean * 1000, 1),
            "total_ms": round(total_ms, 1),
        }

    def start_server(self):
        socket_dir = get_runtime_dir()
        socket_path = get_socket_path()
        if socket_path.exists():
            socket_path.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(socket_path))
        server.listen(5)
        print(f"[Daemon] Listening on Unix socket: {socket_path}")
        try:
            while True:
                conn, _ = server.accept()
                try:
                    data = conn.recv(4096).decode("utf-8")
                    if not data:
                        continue
                    req = json.loads(data)
                    action = req.get("action")

                    if action == "ping":
                        conn.sendall(json.dumps({"status": "pong"}).encode("utf-8"))
                    elif action == "process":
                        audio_path = req.get("audio_path")
                        result = self.process_audio(audio_path)
                        conn.sendall(json.dumps(result).encode("utf-8"))
                    elif action == "toggle":
                        if self.recorder.is_recording():
                            self.on_hotkey_stop()
                            conn.sendall(json.dumps({"status": "stopped"}).encode("utf-8"))
                        else:
                            self.on_hotkey_start()
                            conn.sendall(json.dumps({"status": "started"}).encode("utf-8"))
                    else:
                        conn.sendall(json.dumps({"error": f"unknown action {action}"}).encode("utf-8"))
                except Exception as e:
                    try:
                        conn.sendall(json.dumps({"error": str(e)}).encode("utf-8"))
                    except Exception:
                        pass
                finally:
                    conn.close()
        finally:
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            socket_path = get_socket_path()
            if socket_path.exists():
                socket_path.unlink()
            server.close()
