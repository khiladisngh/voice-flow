"""Probe a candidate Ollama cleaner model with fixed multilingual dictation samples.

Usage:
    .venv/bin/python scripts/cleaner_probe.py hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M [--num-gpu 999] [--runs 3]

Prints each sample's p50 latency and the last output so language preservation,
filler removal and "did it answer instead of rewriting" can be judged by eye.
Stop the daemon first if VRAM is tight: `systemctl --user stop voice-flow`.
"""

import statistics
import sys
import time

from voice_flow.cleaner import TextCleaner

SAMPLES = [
    (
        "en",
        "um so i was thinking like uh we should probably refactor the the injector module you know because "
        "the clipboard restore is uh racing with wayland right so um yeah the delay is like three hundred "
        "fifty milliseconds",
    ),
    (
        "en",
        "um why is the the daemon uh not picking up the new model after i changed config dot json like do i "
        "need to run make restart or is it uh reading it dynamically",
    ),
    (
        "hi",
        "तो मैं यह कह रहा था कि उम्म हमें यह फीचर कल तक बना देना चाहिए मतलब उह पहले बैकएंड फिर फ्रंटएंड और "
        "टेस्टिंग शाम तक हो जाएगी",
    ),
    (
        "hi",
        "haan to main keh raha tha ki uh yeh feature kal tak ready ho jayega you know matlab uh basically "
        "hum log pehle backend karenge phir uh frontend aur testing shaam tak",
    ),
    (
        "de",
        "also ähm ich wollte nur sagen dass wir äh das meeting auf montag verschieben müssen weil ähm der "
        "kunde keine zeit hat",
    ),
]


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print(__doc__)
        return 2
    model = args[0]
    options: dict = {}
    runs = 3
    if "--num-gpu" in args:
        options["num_gpu"] = int(args[args.index("--num-gpu") + 1])
    if "--runs" in args:
        runs = int(args[args.index("--runs") + 1])

    cleaner = TextCleaner(model=model, options=options, keep_alive="2m", timeout=120.0)
    if not cleaner.warm_up():
        print(f"[Probe] {model} did not load; is it pulled?")
        return 1

    all_p50 = []
    for lang, text in SAMPLES:
        latencies, out = [], ""
        for _ in range(runs):
            t0 = time.perf_counter()
            out = cleaner.clean(text, language=lang)
            latencies.append((time.perf_counter() - t0) * 1000)
        p50 = statistics.median(latencies)
        all_p50.append(p50)
        print(f"\n[{lang}] p50={p50:.0f} ms\n  in : {text}\n  out: {out}")
    print(f"\nmedian over samples: {statistics.median(all_p50):.0f} ms")
    cleaner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
