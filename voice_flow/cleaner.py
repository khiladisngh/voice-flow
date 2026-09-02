import requests

SYSTEM_PROMPT = """You are a specialized speech-to-text post-processor.
Your job is to convert spoken stream-of-consciousness text into polished, readable written text:
- Strip verbal hesitations, filler words, and stutters (e.g., "um", "uh", "like", "you know", "kind of").
- Add proper punctuation, capitalization, and logical sentence breaks.
- Format numbers, dates, times, units, and technical terms appropriately.
- Preserve the exact meaning, tone, and specific vocabulary of the speaker.
- Do NOT add polite greetings, introductory phrases, or conversational commentary.
- Return ONLY the finalized text, with no quotes or explanations."""


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
                "num_ctx": 2048,
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

    def clean(self, raw_text: str) -> str:
        """Post-process speech text, falling back to the raw transcript."""
        if not raw_text:
            return ""
        raw_text = raw_text.strip()
        if not raw_text or len(raw_text.split()) < 3:
            # Very short text (1-2 words) rarely needs LLM cleanup
            return raw_text

        prompt = f"{SYSTEM_PROMPT}\n\n<spoken_text>\n{raw_text}\n</spoken_text>\n\nClean Output:"

        try:
            resp = self.session.post(
                self.ollama_url,
                json=self._payload(prompt, max(128, len(raw_text.split()) * 3)),
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                print(f"[Cleaner] Ollama returned HTTP {resp.status_code}; pasting raw transcript")
                return raw_text

            cleaned = resp.json().get("response", "").strip()
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
