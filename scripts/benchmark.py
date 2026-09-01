#!/usr/bin/env python
"""Reproduce the latency and memory figures published in the README.

Generates speech with espeak-ng, runs it through the real transcriber and
cleaner, and reports medians over warm runs. Requires the project venv plus
espeak-ng, and a running Ollama if cleanup is enabled.

    .venv/bin/python scripts/benchmark.py
"""

from __future__ import annotations

import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice_flow.cleaner import TextCleaner  # noqa: E402
from voice_flow.transcriber import Transcriber  # noqa: E402

PHRASES = [
    "Fix the login bug.",
    "The quick brown fox jumps over the lazy dog.",
    "um so basically we should uh fix the authentication handler before we deploy",
]
REPS = 5


def synthesize(text: str, path: Path) -> float:
    subprocess.run(
        ["espeak-ng", "-w", str(path), "-s", "145", text],
        check=True,
        capture_output=True,
    )
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def rss_pss_mb(pattern: str) -> tuple[float, float, int]:
    """Sum RSS and PSS in MB over matching processes; also return the pid count.

    A pid count above zero with a zero total means the process exists but its
    smaps_rollup is not readable by this user (Ollama runs as its own user).
    """
    try:
        pids = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout.split()
    except FileNotFoundError:
        return (0.0, 0.0, 0)

    rss = pss = 0
    for pid in pids:
        rollup = Path(f"/proc/{pid}/smaps_rollup")
        if not rollup.exists():
            continue
        try:
            for line in rollup.read_text().splitlines():
                if line.startswith("Rss:"):
                    rss += int(line.split()[1])
                elif line.startswith("Pss:"):
                    pss += int(line.split()[1])
        except OSError:
            continue
    return (rss / 1024, pss / 1024, len(pids))


def main() -> int:
    if not shutil.which("espeak-ng"):
        print("espeak-ng not found; install it to generate benchmark audio", file=sys.stderr)
        return 1

    # The daemon already holds a Whisper model in VRAM. Loading a second one
    # here exhausts an 8 GB card, so refuse up front with something actionable
    # rather than dying on a CUDA OOM deep inside ctranslate2.
    _rss, _pss, daemon_procs = rss_pss_mb("voice_flow.main daemon")
    if daemon_procs:
        print(
            "The voice-flow daemon is running and already holds a Whisper model in\n"
            "VRAM. Loading a second copy would exhaust the GPU. Stop it first:\n\n"
            "    systemctl --user stop voice-flow\n"
            "    .venv/bin/python scripts/benchmark.py\n"
            "    systemctl --user start voice-flow\n",
            file=sys.stderr,
        )
        return 1

    transcriber = Transcriber()
    cleaner = TextCleaner()
    cleaner.warm_up()

    with tempfile.TemporaryDirectory() as tmp:
        clips = []
        for i, phrase in enumerate(PHRASES):
            path = Path(tmp) / f"clip{i}.wav"
            clips.append((synthesize(phrase, path), path))

        print(f"{'audio':>8}{'stt p50':>11}{'clean p50':>12}{'total p50':>12}")
        print("-" * 43)
        for duration, path in clips:
            transcriber.transcribe(str(path))  # discard warm-up run
            stt_ms, clean_ms = [], []
            for _ in range(REPS):
                t0 = time.perf_counter()
                raw, _lang, _dur = transcriber.transcribe(str(path))
                stt_ms.append((time.perf_counter() - t0) * 1000)
                t1 = time.perf_counter()
                cleaner.clean(raw)
                clean_ms.append((time.perf_counter() - t1) * 1000)
            s = statistics.median(stt_ms)
            c = statistics.median(clean_ms)
            print(f"{duration:>7.1f}s{s:>10.0f}ms{c:>11.0f}ms{s + c:>11.0f}ms")

    print("\nInjection")
    print("-" * 43)
    print("uinput and the clipboard helpers are mocked, so this never writes")
    print("your real clipboard. Measured separately below.")
    try:
        from unittest.mock import MagicMock, patch

        from voice_flow.injector import TextInjector

        for restore in (True, False):
            with (
                patch(
                    "voice_flow.injector.evdev.UInput",
                    side_effect=lambda *a, **k: MagicMock(),
                ),
                patch("voice_flow.injector.TextInjector._set_clipboard"),
                patch(
                    "voice_flow.injector.TextInjector._get_current_clipboard",
                    return_value=b"previous",
                ),
            ):
                inj = TextInjector(restore_clipboard=restore)
                samples = []
                for _ in range(REPS):
                    t0 = time.perf_counter()
                    inj.paste("benchmark payload")
                    samples.append((time.perf_counter() - t0) * 1000)
                inj.close()
            label = "restore_clipboard=True " if restore else "restore_clipboard=False"
            print(f"{label}  p50 {statistics.median(samples):>7.0f} ms")
    except Exception as exc:  # noqa: BLE001 - a benchmark must not hard-fail
        print(f"skipped ({exc.__class__.__name__})")

    # Clipboard I/O, measured by writing the clipboard's own current contents
    # back to it. Idempotent, so it cannot lose data even if it races the user.
    if shutil.which("wl-copy") and shutil.which("wl-paste"):
        current = subprocess.run(["wl-paste", "--no-newline"], capture_output=True).stdout
        io_samples = []
        for _ in range(REPS):
            t0 = time.perf_counter()
            subprocess.run(["wl-copy"], input=current, check=False)
            subprocess.run(["wl-paste", "--no-newline"], capture_output=True)
            io_samples.append((time.perf_counter() - t0) * 1000)
        print(f"wl-copy + wl-paste       p50 {statistics.median(io_samples):>7.0f} ms")
    else:
        print("wl-clipboard not installed; skipping clipboard I/O measurement")

    print("\nMemory (sum over matching processes)")
    print("-" * 43)
    for pattern, label in [
        ("voice_flow.main daemon", "voice-flow daemon"),
        ("llama-server", "ollama llama-server"),
    ]:
        rss, pss, n = rss_pss_mb(pattern)
        if n and rss:
            print(f"{label:<24}RSS {rss:>7.1f} MB  PSS {pss:>7.1f} MB")
        elif n:
            print(f"{label:<24}{n} process(es), smaps not readable by this user")
        else:
            print(f"{label:<24}not running")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
