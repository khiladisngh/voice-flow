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


# num_ctx (4096) bounds prompt + generation together. Past this many words the
# request would overflow the window and the model would silently clean a
# truncated prompt, so paste the raw transcript instead of losing its start.
MAX_CLEAN_WORDS = 500


class TextCleaner:
    """Polishes a raw transcript with a local Ollama model.

    Every failure path degrades to the raw transcript rather than losing the
    user's words, but the degradation is logged: a silent fallback is
    indistinguishable from the cleaner working badly.

    Timing notes, measured on this project's reference machine:
      - warm model: ~66 ms
      - reload with the weights in the OS page cache: ~1.8 s
      - genuine cold load (post-reboot): up to ~13 s
    Hence a default timeout well above the warm case, plus `keep_alive` to stop
    Ollama evicting the model after its ~5 minute idle default. Without the
    pin, the first dictation after any idle gap pays the reload cost.
    """

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
                "num_ctx": 4096,
                **self.options,
            },
        }

    def warm_up(self) -> bool:
        """Load the model into VRAM ahead of the first dictation.

        Called at daemon start-up so the reload cost is paid before the user is
        waiting on it. Returns True if the model responded.
        """
        try:
            resp = self.session.post(
                self.ollama_url,
                json=self._payload("Reply with OK.", 1),
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except Exception as exc:
            print(f"[Cleaner] Warm-up failed ({exc.__class__.__name__}); cleanup may be slow on first use")
            return False

    def clean(self, raw_text: str, language: str | None = None) -> str:
        """Post-process speech text, falling back to the raw transcript.

        `language` is Whisper's detected code (e.g. "hi"); when given, the prompt
        names it so the model rewrites in that language instead of translating.
        """
        if not raw_text:
            return ""
        raw_text = raw_text.strip()
        words = raw_text.split()
        if not raw_text or len(words) < 3:
            # Very short text (1-2 words) rarely needs LLM cleanup
            return raw_text
        if len(words) > MAX_CLEAN_WORDS:
            print(
                f"[Cleaner] Transcript is {len(words)} words (limit {MAX_CLEAN_WORDS}); "
                "pasting raw transcript"
            )
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
                json=self._payload(prompt, max(128, len(words) * 3)),
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

    def close(self):
        """Close the persistent HTTP session."""
        self.session.close()
