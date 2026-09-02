import json
import os
import signal
import socket
import sys

from voice_flow.paths import get_config_path, get_socket_path
from voice_flow.recorder import AudioRecorder


def _restore_default_sigpipe() -> None:
    """Exit quietly when stdout closes, the way Unix CLIs are expected to.

    Only for short-lived subcommands. This MUST NOT apply to the daemon: with
    SIG_DFL, a client that disconnects mid-response would deliver SIGPIPE at
    conn.sendall() and terminate the whole daemon, instead of raising a
    BrokenPipeError that the request handler catches.
    """
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def load_config() -> dict:
    """Load settings from the first config file that exists, else defaults."""
    path = get_config_path()
    if path is None:
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[Config] Ignoring unreadable {path}: {exc.__class__.__name__}")
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
    from voice_flow.cleaner import TextCleaner
    from voice_flow.injector import TextInjector
    from voice_flow.transcriber import Transcriber

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

    pasted = False
    if final_text:
        injector = TextInjector(restore_clipboard=ui_cfg.get("restore_clipboard", True))
        pasted = bool(injector.paste(final_text))

    return {"status": "ok", "raw": raw_text, "cleaned": final_text, "pasted": pasted}


def build_recorder(config: dict) -> AudioRecorder:
    """Construct an AudioRecorder from config.

    `audio.temp_file` of "auto" (or absent) defers to voice_flow.paths, which
    resolves $XDG_RUNTIME_DIR/voice-flow at mode 0700. Never default to a
    world-writable location such as /dev/shm.
    """
    audio_cfg = config.get("audio", {})
    ui_cfg = config.get("ui", {})
    temp_file = audio_cfg.get("temp_file", "auto")
    return AudioRecorder(
        audio_path=None if temp_file == "auto" else temp_file,
        sample_rate=audio_cfg.get("sample_rate", 16000),
        channels=audio_cfg.get("channels", 1),
        sound_feedback=ui_cfg.get("sound_feedback", True),
        notifications=ui_cfg.get("notifications", True),
    )


def handle_toggle(config: dict):
    recorder = build_recorder(config)

    if recorder.is_recording():
        audio_file = recorder.stop()
        if not audio_file:
            print("No audio captured.")
            return

        # Attempt sending to warm daemon first (for ~200ms latency)
        try:
            res = send_to_daemon({"action": "process", "audio_path": audio_file})
            pasted_tag = "Pasted" if res.get("pasted", True) else "Paste FAILED"
            print(f"{pasted_tag}: {res.get('cleaned')} ({res.get('total_ms')}ms)")
        except (TimeoutError, ConnectionError, Exception):
            # Fallback to standalone mode if daemon is not running
            print("Daemon not running, processing standalone...")
            res = run_standalone_process(config, audio_file)
            pasted_tag = "Pasted" if res.get("pasted", True) else "Paste FAILED"
            print(f"{pasted_tag}: {res.get('cleaned')}")
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

    # Long-lived daemon must keep Python's SIGPIPE handling; see the docstring.
    if cmd != "daemon":
        _restore_default_sigpipe()

    if cmd == "toggle":
        handle_toggle(config)
    elif cmd == "record-start":
        rec = build_recorder(config)
        rec.start()
    elif cmd == "record-stop":
        rec = build_recorder(config)
        audio_file = rec.stop()
        if audio_file:
            try:
                res = send_to_daemon({"action": "process", "audio_path": audio_file})
                pasted_tag = "Pasted" if res.get("pasted", True) else "Paste FAILED"
                print(f"{pasted_tag}: {res.get('cleaned')} ({res.get('total_ms')}ms)")
            except Exception:
                res = run_standalone_process(config, audio_file)
                pasted_tag = "Pasted" if res.get("pasted", True) else "Paste FAILED"
                print(f"{pasted_tag}: {res.get('cleaned')}")
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
        uinput_ok = os.access("/dev/uinput", os.W_OK)
        print(f"Daemon running: {'YES (warm in GPU)' if daemon_ok else 'NO'}")
        print(f"Recording active: {rec.is_recording()}")
        print(f"Uinput writable: {'YES' if uinput_ok else 'NO (cannot synthesize paste)'}")
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: voice-flow [toggle|record-start|record-stop|daemon|status]")


if __name__ == "__main__":
    main()
