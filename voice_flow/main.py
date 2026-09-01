import sys
import os
import json
import time
import socket
from pathlib import Path
from voice_flow.recorder import AudioRecorder
from voice_flow.paths import get_socket_path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
SOCKET_PATH = get_socket_path()

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}

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

def run_standalone_process(config: dict, audio_path: str):
    from voice_flow.transcriber import Transcriber
    from voice_flow.cleaner import TextCleaner
    from voice_flow.injector import TextInjector

    stt_cfg = config.get("stt", {})
    cleaner_cfg = config.get("cleaner", {})
    ui_cfg = config.get("ui", {})

    transcriber = Transcriber(
        model_size=stt_cfg.get("model_size", "large-v3-turbo"),
        device=stt_cfg.get("device", "cuda"),
        compute_type=stt_cfg.get("compute_type", "int8_float16"),
        language=stt_cfg.get("language"),
    )
    raw_text, lang, duration = transcriber.transcribe(audio_path)

    final_text = raw_text
    if cleaner_cfg.get("enabled", True) and raw_text:
        cleaner = TextCleaner(
            ollama_url=cleaner_cfg.get("ollama_url", "http://localhost:11434/api/generate"),
            model=cleaner_cfg.get("model", "qwen2.5:1.5b"),
            temperature=cleaner_cfg.get("temperature", 0.1),
        )
        final_text = cleaner.clean(raw_text)

    if final_text:
        injector = TextInjector(restore_clipboard=ui_cfg.get("restore_clipboard", True))
        injector.paste(final_text)

    return {"status": "ok", "raw": raw_text, "cleaned": final_text}

def handle_toggle(config: dict):
    audio_cfg = config.get("audio", {})
    ui_cfg = config.get("ui", {})
    recorder = AudioRecorder(
        audio_path=audio_cfg.get("temp_file", "/dev/shm/voice_flow_record.wav"),
        sample_rate=audio_cfg.get("sample_rate", 16000),
        channels=audio_cfg.get("channels", 1),
        sound_feedback=ui_cfg.get("sound_feedback", True),
        notifications=ui_cfg.get("notifications", True),
    )

    if recorder.is_recording():
        audio_file = recorder.stop()
        if not audio_file:
            print("No audio captured.")
            return

        # Attempt sending to warm daemon first (for ~200ms latency)
        try:
            res = send_to_daemon({"action": "process", "audio_path": audio_file})
            print(f"Pasted: {res.get('cleaned')} ({res.get('total_ms')}ms)")
        except (ConnectionError, socket.timeout, Exception) as e:
            # Fallback to standalone mode if daemon is not running
            print("Daemon not running, processing standalone...")
            res = run_standalone_process(config, audio_file)
            print(f"Pasted: {res.get('cleaned')}")
    else:
        recorder.start()
        print("Listening... (Press hotkey again to finish & paste)")

def handle_daemon(config: dict):
    from voice_flow.daemon import VoiceFlowDaemon
    daemon = VoiceFlowDaemon(config)
    daemon.start_server()

def main():
    config = load_config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "toggle"

    if cmd == "toggle":
        handle_toggle(config)
    elif cmd == "record-start":
        audio_cfg = config.get("audio", {})
        ui_cfg = config.get("ui", {})
        rec = AudioRecorder(
            audio_path=audio_cfg.get("temp_file", "/dev/shm/voice_flow_record.wav"),
            sound_feedback=ui_cfg.get("sound_feedback", True),
            notifications=ui_cfg.get("notifications", True),
        )
        rec.start()
    elif cmd == "record-stop":
        audio_cfg = config.get("audio", {})
        ui_cfg = config.get("ui", {})
        rec = AudioRecorder(
            audio_path=audio_cfg.get("temp_file", "/dev/shm/voice_flow_record.wav"),
            sound_feedback=ui_cfg.get("sound_feedback", True),
            notifications=ui_cfg.get("notifications", True),
        )
        audio_file = rec.stop()
        if audio_file:
            try:
                res = send_to_daemon({"action": "process", "audio_path": audio_file})
                print(f"Pasted: {res.get('cleaned')} ({res.get('total_ms')}ms)")
            except Exception:
                res = run_standalone_process(config, audio_file)
                print(f"Pasted: {res.get('cleaned')}")
    elif cmd == "daemon":
        handle_daemon(config)
    elif cmd == "status":
        daemon_ok = False
        if get_socket_path().exists():
            try:
                res = send_to_daemon({"action": "ping"}, timeout=1.0)
                daemon_ok = res.get("status") == "pong"
            except Exception:
                pass
        rec = AudioRecorder()
        print(f"Daemon running: {'YES (warm in GPU)' if daemon_ok else 'NO'}")
        print(f"Recording active: {rec.is_recording()}")
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: voice-flow [toggle|record-start|record-stop|daemon|status]")

if __name__ == "__main__":
    main()
