# Multilingual Cleaner Model Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `qwen2.5:1.5b` with a Qwen3.5 cleaner that preserves English, Hindi and Hinglish, never answers the dictation, and can be swapped for any Ollama model by editing `cleaner.model` alone.

**Architecture:** `TextCleaner` keeps its single `/api/generate` call but (1) always sends `think: false` so thinking-capable models respond directly, (2) merges a caller-supplied `options` dict into the Ollama options so per-model tuning (`num_gpu`, `top_k`, …) lives in config, (3) accepts Whisper's detected language and names it in the prompt, which is what stops small models from translating, and (4) strips any leaked `<think>…</think>` block as a fail-safe. `daemon.py` and `main.py` pass the language they already receive from `Transcriber.transcribe()`. Bundled config, docs, README and CHANGELOG move to the new default together.

**Tech Stack:** Python 3.12, `requests`, Ollama ≥ 0.9 (`think` parameter), pytest with `unittest.mock`.

**Spec:** This document's "Design decisions" section below; measurements in "Evidence".

## Global Constraints

- Ruff `line-length = 110`, `target-version = "py312"`; Prettier owns Markdown/JSON. Never format `.md` with ruff.
- Logging is `print()` with a bracketed tag: `[Cleaner]`, `[Daemon]`.
- No custom exceptions; no `async`; no new runtime dependencies.
- `TextCleaner.clean()` must never raise; every failure returns `raw_text`.
- Spoken text stays wrapped in `<spoken_text>` … `</spoken_text>`; the prompt suffix stays `Clean Output:`.
- `main.py` must not import heavy modules at module scope; `TextCleaner` is imported inside `run_standalone_process()` only.
- A user-visible config key change lands in `config.json`, `docs/configuration.md` and `README.md` in the same commit.
- Tests are hermetic: patch `cleaner.session.post` via `patch.object`; never call a real Ollama in tests.
- Conventional Commits; user-visible changes go under `## [Unreleased]` in `CHANGELOG.md`.
- Feature branch off `develop`.

---

## Design decisions

|Decision|Choice|Why|
|---|---|---|
|Default model|`hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M`|Best English/coding cleanup of everything that fits an 8 GB RTX 3070 next to Whisper; with a language hint it kept Hindi 3/3, Hinglish 3/3, German 3/3. 226–370 ms p50 when fully on GPU.|
|Low-VRAM alternative|`hf.co/unsloth/Qwen3.5-0.8B-GGUF:Q8_0`|1.1 GB, ~200 ms, never switched language in any run, but leaves some fillers. Documented, not default.|
|Thinking|Always send `"think": false`|Qwen3.5 thinks by default and has no `/nothink` switch. Ollama accepts `think: false` for non-thinking models too (verified against `qwen2.5:1.5b`), so no capability probe is needed and any model is a one-line swap.|
|Per-model tuning|New `cleaner.options` dict merged into Ollama `options`|`num_gpu: 999` is the difference between 0.35 s (100 % GPU) and 1.4 s (Ollama's conservative estimate offloads 15 % to CPU) for the 2B on this machine. Generic dict covers `top_k`/`min_p` for other models without more keys.|
|Language steering|`clean(raw_text, language)` adds "The spoken text is in Hindi. Write the output in Hindi…" when Whisper reports a language|"Same language as input" phrasing failed on 2B in 4 of 6 runs; naming the language succeeded 9/9 on Hindi/Hinglish/German.|
|Model swap mechanism|Edit `cleaner.model`, `make restart`|Daemon already warms the model at start. Hot-swap IPC would grow the single-request protocol for no measured need.|
|Prompt|Hardcoded, no code-like examples, no "developer" framing|Examples such as `pyproject.toml` in the prompt made 2B emit a fake TOML block; "developer dictating to coding agents" framing made it translate Hindi to English. Both measured.|
|`num_ctx`|Fixed at 2048 in code|Prompt ≈ 250 tokens + `num_predict ≤ 3 × words`. Qwen3.5 enforces a 2048 minimum anyway; smaller than Ollama's 4096 default saves VRAM for every model.|

Out of scope, noted for later: `Transcriber` passes an English `initial_prompt` to Whisper, which may bias Hinglish detection towards `en` (the one case where the 2B still translated). Not touched here because `transcriber.py` has no unit tests and needs CUDA to verify.

## Evidence

Measured on the reference machine (RTX 3070 8 GB, daemon + Whisper resident, desktop apps open), 3 runs per sample, real `SYSTEM_PROMPT` wrapper, `temperature 0.1`:

|Model|VRAM|p50|Hindi kept|Hinglish kept|Answers instead of rewriting|
|---|---|---|---|---|---|
|`qwen2.5:1.5b`|1.3 GB|170–210 ms|0/9 (translated + hallucinated "firewall")|0/6|Yes (turned "do I need make restart?" into an answer; turned the user's dictation into a fake plan)|
|`Qwen3.5-0.8B Q8_0`|1.4 GB|200–240 ms|9/9|6/6|No, but echoes input unchanged on 2/6 coding samples|
|`Qwen3.5-2B Q4_K_M`, no language hint|2.35 GB|226–1400 ms|4/9|3/6|No|
|`Qwen3.5-2B Q4_K_M`, language hint, `num_gpu 999`|2.35 GB|218–377 ms|3/3|3/3 (`hi`), 2/3 (`en`)|No|
|`Qwen3.5-4B Q4_K_M`|3.3 GB, 47 % GPU|4.7 s|3/3|3/3|No — too slow|

Gemma 4 E2B/E4B (smallest Ollama tag 4.3 GB) and Qwen3.6/3.8 (≥ 27B) do not fit beside Whisper and were not run.

## File structure

|File|Responsibility in this change|
|---|---|
|`voice_flow/cleaner.py`|New `SYSTEM_PROMPT`; `LANGUAGE_NAMES`; `TextCleaner(options=…)`; `_payload()` adds `think`, `num_ctx`, merged options; `clean(raw_text, language=None)` builds the language line and strips `<think>` blocks.|
|`voice_flow/daemon.py`|Pass `options=cleaner_cfg.get("options", {})`; pass `lang` to `clean()`; new default model string.|
|`voice_flow/main.py`|Same two changes in `run_standalone_process()`.|
|`config.json`|`cleaner.model` → new default; add `"options": {}`.|
|`tests/test_cleaner.py`|Payload contract (`think`, `num_ctx`, options merge), language line, `<think>` stripping, unknown-language passthrough.|
|`tests/test_ipc.py`|Daemon passes `lang` to the cleaner.|
|`scripts/cleaner_probe.py`|Repeatable multilingual probe for evaluating a candidate model before swapping (uses real Ollama; not a test).|
|`docs/configuration.md`, `docs/installation.md`, `docs/troubleshooting.md`, `docs/architecture.md`, `docs/index.md`, `README.md`, `AGENTS.md`, `CHANGELOG.md`|Model name, new key, pull command, model table, timeout correction.|

---

### Task 1: Payload contract — `think: false`, `num_ctx`, merged `options`

**Files:**
- Modify: `voice_flow/cleaner.py:29-54`
- Test: `tests/test_cleaner.py`

**Interfaces:**
- Produces: `TextCleaner.__init__(..., options: dict | None = None)`; `TextCleaner._payload(prompt: str, num_predict: int) -> dict` whose result has top-level `"think": False` and `options == {"temperature", "num_predict", "num_ctx": 2048, **self.options}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cleaner.py`:

```python
def test_payload_disables_thinking_and_pins_context():
    cleaner = TextCleaner()
    payload = cleaner._payload("prompt", 128)
    assert payload["think"] is False
    assert payload["options"]["num_ctx"] == 2048
    assert payload["options"]["temperature"] == cleaner.temperature
    assert payload["options"]["num_predict"] == 128


def test_payload_merges_user_options_over_defaults():
    cleaner = TextCleaner(temperature=0.1, options={"num_gpu": 999, "temperature": 0.0})
    options = cleaner._payload("prompt", 128)["options"]
    assert options["num_gpu"] == 999
    assert options["temperature"] == 0.0  # explicit options win over the temperature kwarg
    assert options["num_predict"] == 128


def test_payload_without_options_has_no_extra_keys():
    options = TextCleaner()._payload("prompt", 128)["options"]
    assert set(options) == {"temperature", "num_predict", "num_ctx"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cleaner.py -k payload -v`
Expected: 3 FAIL — `TypeError: unexpected keyword argument 'options'` and `KeyError: 'think'`.

- [ ] **Step 3: Implement**

In `voice_flow/cleaner.py`, replace the constructor signature and `_payload`:

```python
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        model: str = "hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M",
        temperature: float = 0.1,
        timeout: float = 15.0,
        keep_alive: int | str = -1,
        options: dict | None = None,
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.keep_alive = keep_alive
        # Extra Ollama options merged over the defaults, e.g. {"num_gpu": 999}
        # to force full GPU offload when Ollama's fit estimate is too cautious.
        self.options = dict(options or {})
        self.session = requests.Session()

    def _payload(self, prompt: str, num_predict: int) -> dict:
        return {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            # Thinking models (Qwen3.5, …) reason by default and have no prompt-level
            # switch; Ollama accepts think=false for non-thinking models as well.
            "think": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": num_predict,
                "num_ctx": 2048,
                **self.options,
            },
        }
```

- [ ] **Step 4: Run the cleaner tests**

Run: `.venv/bin/pytest tests/test_cleaner.py -v`
Expected: all PASS (existing `test_clean_prompt_wrapping_with_spoken_text_tags` still passes; it only asserts keys that are unchanged).

- [ ] **Step 5: Commit**

```bash
git add voice_flow/cleaner.py tests/test_cleaner.py
git commit -m "feat(cleaner): disable thinking, pin num_ctx, accept per-model Ollama options"
```

---

### Task 2: Language-aware prompt and `<think>` fail-safe

**Files:**
- Modify: `voice_flow/cleaner.py:1-11` (prompt) and `:73-101` (`clean`)
- Test: `tests/test_cleaner.py`

**Interfaces:**
- Consumes: `_payload()` from Task 1.
- Produces: `SYSTEM_PROMPT: str`; `LANGUAGE_NAMES: dict[str, str]`; `TextCleaner.clean(raw_text: str, language: str | None = None) -> str`; module function `_strip_think(text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cleaner.py`:

```python
from voice_flow.cleaner import LANGUAGE_NAMES, _strip_think


def _ok_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"response": text}
    return resp


def test_clean_names_detected_language_in_prompt():
    cleaner = TextCleaner()
    with patch.object(cleaner.session, "post", return_value=_ok_response("साफ़ किया गया पाठ")) as post:
        cleaner.clean("तो मैं यह कह रहा था कि हमें यह फीचर कल तक बना देना चाहिए", language="hi")
    prompt = post.call_args.kwargs["json"]["prompt"]
    assert "The spoken text is in Hindi. Write the output in Hindi" in prompt
    assert prompt.index(SYSTEM_PROMPT) < prompt.index("The spoken text is in Hindi") < prompt.index("<spoken_text>")
    assert prompt.endswith("</spoken_text>\n\nClean Output:")


def test_clean_without_language_omits_language_line():
    cleaner = TextCleaner()
    with patch.object(cleaner.session, "post", return_value=_ok_response("Cleaned text here.")) as post:
        cleaner.clean("some words that need cleaning up")
    prompt = post.call_args.kwargs["json"]["prompt"]
    assert "The spoken text is in" not in prompt
    assert prompt == f"{SYSTEM_PROMPT}\n\n<spoken_text>\nsome words that need cleaning up\n</spoken_text>\n\nClean Output:"


def test_clean_unknown_language_code_is_passed_through():
    cleaner = TextCleaner()
    with patch.object(cleaner.session, "post", return_value=_ok_response("ok ok ok")) as post:
        cleaner.clean("three words minimum here", language="xx")
    assert "The spoken text is in xx. Write the output in xx" in post.call_args.kwargs["json"]["prompt"]


def test_language_names_cover_project_languages():
    assert LANGUAGE_NAMES["en"] == "English"
    assert LANGUAGE_NAMES["hi"] == "Hindi"


def test_strip_think_removes_leaked_reasoning_block():
    assert _strip_think("<think>\nplanning...\n</think>\n\nFinal text.") == "Final text."
    assert _strip_think("Final text.") == "Final text."
    assert _strip_think("<think>unterminated") == "<think>unterminated"


def test_clean_strips_think_block_from_response():
    cleaner = TextCleaner()
    with patch.object(cleaner.session, "post", return_value=_ok_response("<think>x</think>\n\nClean.")):
        assert cleaner.clean("words that need cleaning up") == "Clean."


def test_clean_think_only_response_falls_back_to_raw():
    cleaner = TextCleaner()
    with patch.object(cleaner.session, "post", return_value=_ok_response("<think>only reasoning</think>")):
        assert cleaner.clean("words that need cleaning up") == "words that need cleaning up"


def test_system_prompt_has_no_code_like_examples():
    # Measured: file-name examples in the prompt made Qwen3.5-2B emit a fake TOML block.
    for token in (".py", ".toml", "git ", "`"):
        assert token not in SYSTEM_PROMPT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cleaner.py -v`
Expected: FAIL at import — `ImportError: cannot import name 'LANGUAGE_NAMES'`.

- [ ] **Step 3: Implement**

Replace lines 1–11 of `voice_flow/cleaner.py`:

```python
import re

import requests

SYSTEM_PROMPT = """You are a specialized speech-to-text post-processor.
Your job is to convert spoken stream-of-consciousness text into polished, readable written text:
- Strip verbal hesitations, filler words, and stutters (e.g., "um", "uh", "like", "you know", "kind of").
- Add proper punctuation, capitalization, and logical sentence breaks.
- Format numbers, dates, times, units, and technical terms appropriately.
- Keep code identifiers, file names, commands, and technical terms exactly as spoken.
- Preserve the exact meaning, tone, and specific vocabulary of the speaker; keep questions as questions and instructions as instructions.
- Never translate, answer, or summarize the spoken text; only rewrite it.
- Do NOT add polite greetings, introductory phrases, or conversational commentary.
- Return ONLY the finalized text, with no quotes or explanations."""

# Whisper language codes -> names the prompt can use. Naming the language is what
# stops small models from translating; "same language as the input" was not enough.
LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "ur": "Urdu",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "tr": "Turkish",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}

_THINK_BLOCK = re.compile(r"\A\s*<think>.*?</think>\s*", re.DOTALL)


def _strip_think(text: str) -> str:
    """Drop a leading <think>…</think> block if a thinking model leaked one into `response`."""
    return _THINK_BLOCK.sub("", text, count=1)
```

Replace `clean()` (lines 73–101 in the pre-change file):

```python
    def clean(self, raw_text: str, language: str | None = None) -> str:
        """Post-process speech text, falling back to the raw transcript.

        `language` is Whisper's detected code (e.g. "hi"); when given, the prompt
        names it so the model rewrites in that language instead of translating.
        """
        if not raw_text:
            return ""
        raw_text = raw_text.strip()
        if not raw_text or len(raw_text.split()) < 3:
            # Very short text (1-2 words) rarely needs LLM cleanup
            return raw_text

        prompt = SYSTEM_PROMPT
        if language:
            name = LANGUAGE_NAMES.get(language, language)
            prompt += (
                f"\n\nThe spoken text is in {name}. Write the output in {name}, "
                "in the same script the speaker used."
            )
        prompt += f"\n\n<spoken_text>\n{raw_text}\n</spoken_text>\n\nClean Output:"

        try:
            resp = self.session.post(
                self.ollama_url,
                json=self._payload(prompt, max(128, len(raw_text.split()) * 3)),
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                print(f"[Cleaner] Ollama returned HTTP {resp.status_code}; pasting raw transcript")
                return raw_text

            cleaned = _strip_think(resp.json().get("response", "")).strip()
            if not cleaned:
                print("[Cleaner] Ollama returned an empty response; pasting raw transcript")
                return raw_text
            return cleaned
        except Exception as exc:
            print(f"[Cleaner] Cleanup unavailable ({exc.__class__.__name__}); pasting raw transcript")
            return raw_text
```

- [ ] **Step 4: Run the cleaner tests**

Run: `.venv/bin/pytest tests/test_cleaner.py -v`
Expected: all PASS, including the pre-existing `test_clean_prompt_injection_containment` (it asserts the wrapper, which is unchanged when `language` is `None`).

- [ ] **Step 5: Commit**

```bash
git add voice_flow/cleaner.py tests/test_cleaner.py
git commit -m "feat(cleaner): name the detected language in the prompt and strip leaked <think> blocks"
```

---

### Task 3: Wire language and options through daemon and standalone paths

**Files:**
- Modify: `voice_flow/daemon.py:37-45` and `:94-99`
- Modify: `voice_flow/main.py:71-77`
- Test: `tests/test_ipc.py`

**Interfaces:**
- Consumes: `TextCleaner(options=…)` (Task 1), `clean(raw_text, language)` (Task 2).

- [ ] **Step 1: Write the failing test**

Open `tests/test_ipc.py` and find the existing daemon fixture/pattern that patches `voice_flow.daemon.Transcriber`, `voice_flow.daemon.TextCleaner`, `voice_flow.daemon.TextInjector`, `voice_flow.daemon.AudioRecorder`, `voice_flow.daemon.GlobalHotkeyListener` (used by `test_daemon_signal_handling_and_lifecycle` at ~L190). Reuse that patching style; add:

```python
def test_daemon_process_audio_passes_detected_language_to_cleaner():
    with (
        patch("voice_flow.daemon.Transcriber") as transcriber_cls,
        patch("voice_flow.daemon.TextCleaner") as cleaner_cls,
        patch("voice_flow.daemon.TextInjector") as injector_cls,
        patch("voice_flow.daemon.AudioRecorder"),
        patch("voice_flow.daemon.GlobalHotkeyListener"),
    ):
        transcriber_cls.return_value.transcribe.return_value = ("raw hindi words here", "hi", 1.2)
        cleaner_cls.return_value.warm_up.return_value = True
        cleaner_cls.return_value.clean.return_value = "clean"
        injector_cls.return_value.paste.return_value = True

        from voice_flow.daemon import VoiceFlowDaemon

        daemon = VoiceFlowDaemon({"cleaner": {"options": {"num_gpu": 999}}, "hotkey": {"enabled": False}})
        result = daemon.process_audio("/nonexistent.wav")

    cleaner_cls.assert_called_once()
    assert cleaner_cls.call_args.kwargs["options"] == {"num_gpu": 999}
    cleaner_cls.return_value.clean.assert_called_once_with("raw hindi words here", language="hi")
    assert result["language"] == "hi"
    assert result["cleaned"] == "clean"
```

If the existing tests construct the daemon differently (e.g. a helper), match that helper instead of the inline `with` block — but keep the three assertions.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ipc.py -k passes_detected_language -v`
Expected: FAIL — `KeyError: 'options'` on `call_args.kwargs["options"]`.

- [ ] **Step 3: Implement daemon changes**

In `voice_flow/daemon.py` lines 37–45:

```python
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
```

Line 98: `final_text = self.cleaner.clean(raw_text)` → `final_text = self.cleaner.clean(raw_text, language=lang)`.

- [ ] **Step 4: Implement standalone changes**

In `voice_flow/main.py` lines 71–77:

```python
    if cleaner_cfg.get("enabled", True) and raw_text:
        cleaner = TextCleaner(
            ollama_url=cleaner_cfg.get("ollama_url", "http://localhost:11434/api/generate"),
            model=cleaner_cfg.get("model", "hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M"),
            temperature=cleaner_cfg.get("temperature", 0.1),
            options=cleaner_cfg.get("options", {}),
        )
        final_text = cleaner.clean(raw_text, language=lang)
```

- [ ] **Step 5: Run the IPC and cleaner tests**

Run: `.venv/bin/pytest tests/test_ipc.py tests/test_cleaner.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add voice_flow/daemon.py voice_flow/main.py tests/test_ipc.py
git commit -m "feat: pass Whisper language and cleaner.options through daemon and standalone paths"
```

---

### Task 4: Model probe script for evaluating swaps

**Files:**
- Create: `scripts/cleaner_probe.py`
- Modify: `AGENTS.md` (Key Directories row for `scripts/`), `docs/development.md` (next to the benchmark section)

**Interfaces:**
- Consumes: `voice_flow.cleaner.TextCleaner` public API only (`TextCleaner(model=…, options=…)`, `.clean(text, language=…)`).

This is the repeatable version of the ad-hoc probes that produced the Evidence table. It is not a test (it needs a live Ollama) and is never run by CI.

- [ ] **Step 1: Create the script**

```python
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
    ("en", "um so i was thinking like uh we should probably refactor the the injector module you know because "
           "the clipboard restore is uh racing with wayland right so um yeah the delay is like three hundred "
           "fifty milliseconds"),
    ("en", "um why is the the daemon uh not picking up the new model after i changed config dot json like do i "
           "need to run make restart or is it uh reading it dynamically"),
    ("hi", "तो मैं यह कह रहा था कि उम्म हमें यह फीचर कल तक बना देना चाहिए मतलब उह पहले बैकएंड फिर फ्रंटएंड और "
           "टेस्टिंग शाम तक हो जाएगी"),
    ("hi", "haan to main keh raha tha ki uh yeh feature kal tak ready ho jayega you know matlab uh basically "
           "hum log pehle backend karenge phir uh frontend aur testing shaam tak"),
    ("de", "also ähm ich wollte nur sagen dass wir äh das meeting auf montag verschieben müssen weil ähm der "
           "kunde keine zeit hat"),
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
```

- [ ] **Step 2: Smoke-run it against the currently pulled model**

Run: `.venv/bin/python scripts/cleaner_probe.py hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M --num-gpu 999`
Expected: five samples printed, Hindi output in Devanagari, Hinglish output still Hinglish, English outputs free of "um"/"uh", median well under 1000 ms. (`ollama ps` during the run shows `100% GPU`.)

- [ ] **Step 3: Lint**

Run: `.venv/bin/ruff check scripts/cleaner_probe.py && .venv/bin/ruff format --check scripts/cleaner_probe.py`
Expected: clean.

- [ ] **Step 4: Update the two docs that list `scripts/`**

`AGENTS.md` Key Directories row: `|`scripts/`|`benchmark.py` and `cleaner_probe.py` (evaluate a candidate cleaner model before swapping).|`

`docs/development.md`, after the benchmark section, add:

```markdown
### Evaluating a cleaner model

Before changing `cleaner.model`, run the probe against the candidate. It uses the
real prompt and a fixed set of English, Hindi, Hinglish and German dictations, and
prints latency plus the output so you can see whether the model translates,
answers, or leaves fillers behind:

```bash
.venv/bin/python scripts/cleaner_probe.py hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M --num-gpu 999
```
```

- [ ] **Step 5: Commit**

```bash
git add scripts/cleaner_probe.py AGENTS.md docs/development.md
git commit -m "feat(scripts): add cleaner_probe.py for evaluating candidate cleaner models"
```

---

### Task 5: Config, docs, README, CHANGELOG cutover

**Files:**
- Modify: `config.json:13-20`
- Modify: `README.md:43,142,201-203,228,244`
- Modify: `docs/configuration.md:30-36,177-202`
- Modify: `docs/installation.md:112,196-198`
- Modify: `docs/troubleshooting.md:15,281,288,295,303`
- Modify: `docs/architecture.md:14`
- Modify: `docs/index.md:33`
- Modify: `CHANGELOG.md` (`## [Unreleased]`)

- [ ] **Step 1: `config.json`**

```json
  "cleaner": {
    "enabled": true,
    "ollama_url": "http://localhost:11434/api/generate",
    "model": "hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M",
    "temperature": 0.1,
    "timeout_sec": 15.0,
    "keep_alive": -1,
    "options": {}
  },
```

- [ ] **Step 2: `docs/configuration.md`**

Update the sample config block (L30–36) to match Step 1. Replace the `cleaner` table rows and fixed-behaviour list (L183–202) with:

```markdown
| Key                   | Type    | Default                                  | Effect |
| --------------------- | ------- | ---------------------------------------- | ------ |
| `cleaner.enabled`     | boolean | `true`                                   | Whether to post-process at all. `false` pastes the raw Whisper transcript and skips the Ollama connection entirely. |
| `cleaner.ollama_url`  | string  | `"http://localhost:11434/api/generate"`  | Full URL of Ollama's generate endpoint. Point it at another host to use a remote server — note that doing so sends transcripts over the network and breaks the offline guarantee. |
| `cleaner.model`       | string  | `"hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M"` | Any Ollama model name, including `hf.co/<repo>:<quant>` GGUF pulls. Must already be pulled (`ollama pull <name>`). Thinking-capable models are handled automatically (`think` is disabled per request). Restart the daemon after changing it. |
| `cleaner.temperature` | number  | `0.1`                                    | Sampling temperature. Keep it low; cleanup is a rewriting task, and higher values invent words. |
| `cleaner.timeout_sec` | number  | `15.0`                                   | Client timeout per request. Slower than this and the raw transcript is pasted, so a stalled Ollama never blocks dictation. |
| `cleaner.keep_alive`  | int/str | `-1`                                     | Ollama `keep_alive`; `-1` pins the model in VRAM so the first dictation after an idle gap does not pay a reload. |
| `cleaner.options`     | object  | `{}`                                     | Extra Ollama `options` merged over the defaults, for per-model tuning. On an 8 GB GPU shared with Whisper, `{"num_gpu": 999}` forces full offload of the 2B model (≈0.35 s instead of ≈1.4 s when Ollama's estimate leaves 15 % on the CPU). |

### Model choices

Measured on an RTX 3070 (8 GB) with Whisper `large-v3-turbo` resident and a desktop session open:

| Model                                   | VRAM    | Latency (p50) | Notes |
| --------------------------------------- | ------- | ------------- | ----- |
| `hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M`  | ≈2.3 GB | 0.2–0.4 s with `num_gpu: 999`; 1.0–1.4 s otherwise | Default. Best cleanup for English and code-heavy dictation; keeps Hindi, Hinglish and European languages when Whisper reports the language. |
| `hf.co/unsloth/Qwen3.5-0.8B-GGUF:Q8_0`  | ≈1.4 GB | ≈0.2 s        | Low-VRAM option. Never switches language but leaves some fillers behind. |
| `qwen2.5:1.5b` (previous default)       | ≈1.3 GB | ≈0.2 s        | English only in practice: translates Hindi/Hinglish to English and sometimes answers the dictation instead of rewriting it. |

Behaviour that is fixed in code rather than configurable:

- **Language steering.** Whisper's detected language is named in the prompt ("The spoken text is in Hindi…"), which is what keeps small models from translating.
- **Thinking disabled.** Every request sends `think: false`; a leaked `<think>` block is stripped from the response as a fail-safe.
- **Silent fallback.** Any failure — connection refused, non-200 status, empty response — returns the raw transcript. Cleanup can never lose your words.
- **Short-input bypass.** Text of fewer than three words skips the LLM entirely.
- **Adaptive output cap.** `num_predict` is `max(128, word_count * 3)`; `num_ctx` is fixed at 2048.
- **Persistent HTTP session.** Connections are reused across utterances.
```

- [ ] **Step 3: Pull commands and model mentions**

Replace every `ollama pull qwen2.5:1.5b` with `ollama pull hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M` in `README.md:142`, `docs/installation.md:112`, `docs/troubleshooting.md:295`. Replace `ollama list | grep qwen2.5:1.5b` (`troubleshooting.md:281`) with `ollama list | grep Qwen3.5-2B`, the curl example model at `troubleshooting.md:288`, and the log-line examples at `troubleshooting.md:15,303`. Update the Mermaid node text `Ollama qwen2.5:1.5b` in `README.md:244` and `docs/architecture.md:14` to `Ollama Qwen3.5-2B`. Update `docs/installation.md:196-198` to name the new model and the 15 s timeout. Update README config sample (L201–203) to include `"options": {}` and the key table row at L228:

```markdown
| `cleaner.model`             | Ollama model used for cleanup. Default `hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M`; any pulled model works. |
| `cleaner.options`           | Extra Ollama options for the model, e.g. `{"num_gpu": 999}` on an 8 GB GPU.                         |
```

- [ ] **Step 4: Latency tables**

`README.md:43` and `docs/index.md:33` quote `qwen2.5:1.5b` cleanup latency. Change the model name and replace the numbers with fresh measurements from Task 6 Step 3 (do not carry the old numbers over).

- [ ] **Step 5: CHANGELOG**

Under `## [Unreleased]`:

```markdown
### Changed

- Default cleaner model is now `hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M`. The previous `qwen2.5:1.5b` translated Hindi and Hinglish dictation to English and sometimes answered the dictation instead of rewriting it.
- The cleaner names Whisper's detected language in the prompt and always disables model thinking, so any Ollama model — including thinking-capable ones — can be set in `cleaner.model` without code changes.

### Added

- `cleaner.options`: extra Ollama options merged per request (e.g. `{"num_gpu": 999}` to force full GPU offload).
- `scripts/cleaner_probe.py`: multilingual probe for evaluating a candidate cleaner model before swapping.
```

- [ ] **Step 6: Format and build docs**

Run: `npx prettier --write README.md CHANGELOG.md AGENTS.md config.json "docs/**/*.md" && make docs-build`
Expected: Prettier rewrites nothing unexpected; `zensical build --strict` exits 0.

- [ ] **Step 7: Commit**

```bash
git add config.json README.md CHANGELOG.md docs
git commit -m "docs: switch default cleaner to Qwen3.5-2B, document cleaner.options and model choices"
```

---

### Task 6: Live verification and benchmark refresh

**Files:**
- Modify: `README.md:43`, `docs/index.md:33` (numbers only)
- Modify: `~/.config/voice-flow/config.json` if present (user config, not committed)

- [ ] **Step 1: Full suite, lint, hermeticity canary**

```bash
make lint && .venv/bin/pytest -q
printf 'CANARY' | wl-copy && .venv/bin/pytest -q >/dev/null 2>&1 && test "$(wl-paste)" = CANARY && echo "session intact"
```
Expected: lint clean, all tests pass, `session intact`.

- [ ] **Step 2: Restart the daemon on the new model**

If `~/.config/voice-flow/config.json` exists, set `cleaner.model` and `"options": {"num_gpu": 999}` there too (user config shadows the bundled one). Then:

```bash
make restart && make logs
```
Expected in the journal: `[Daemon] Connecting to Ollama cleaner (hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M)...` then `Voice Flow Daemon is warm and ready!`. `ollama ps` shows the model at `100% GPU`.

- [ ] **Step 3: Dictate three utterances and read the journal**

Dictate one English instruction to a coding agent, one Hindi sentence, one Hinglish sentence. In `make logs`, each `[Daemon] Transcribed & pasted:` line must show: no fillers, no translation, no answer, and `clean_ms` under 1000. Record the three `clean_ms` values.

- [ ] **Step 4: Refresh the benchmark tables**

```bash
systemctl --user stop voice-flow
.venv/bin/python scripts/benchmark.py
systemctl --user start voice-flow
```
Put the new cleanup p50/p90/p99 into `README.md:43` and `docs/index.md:33` and update the `Text appears` totals accordingly.

- [ ] **Step 5: Commit and open the PR against `develop`**

```bash
git add README.md docs/index.md
git commit -m "docs: refresh latency tables for the Qwen3.5-2B cleaner"
```

---

## Self-review

- **Coverage:** Every design decision maps to a task — `think`/`options`/`num_ctx` (T1), language + `<think>` + prompt (T2), call sites (T3), swap tooling (T4), config/docs/changelog together (T5), live proof and benchmark numbers (T6).
- **Type consistency:** `TextCleaner(options: dict | None)`, `clean(raw_text: str, language: str | None = None) -> str`, `_strip_think(text: str) -> str`, `LANGUAGE_NAMES: dict[str, str]` are used identically in T1–T4.
- **Hermeticity:** T1–T3 tests patch `cleaner.session.post` or the daemon's component classes; only T4 Step 2 and T6 touch a real Ollama, and neither is collected by pytest.
