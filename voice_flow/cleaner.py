import requests
from typing import Optional

SYSTEM_PROMPT = """You are a specialized speech-to-text post-processor.
Your job is to convert spoken stream-of-consciousness text into polished, readable written text:
- Strip verbal hesitations, filler words, and stutters (e.g., "um", "uh", "like", "you know", "kind of").
- Add proper punctuation, capitalization, and logical sentence breaks.
- Format numbers, dates, times, units, and technical terms appropriately.
- Preserve the exact meaning, tone, and specific vocabulary of the speaker.
- Do NOT add polite greetings, introductory phrases, or conversational commentary.
- Return ONLY the finalized text, with no quotes or explanations."""

class TextCleaner:
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        model: str = "qwen2.5:1.5b",
        temperature: float = 0.1,
        timeout: float = 4.0,
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def clean(self, raw_text: str) -> str:
        """Post-process speech text using local LLM with fallback to raw text."""
        raw_text = raw_text.strip()
        if not raw_text or len(raw_text.split()) < 3:
            # Very short text (1-2 words) rarely needs LLM cleanup
            return raw_text

        prompt = f"{SYSTEM_PROMPT}\n\nSpoken Input:\n{raw_text}\n\nClean Output:"

        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": max(128, len(raw_text.split()) * 3),
                    },
                },
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                cleaned = resp.json().get("response", "").strip()
                # If the LLM returned empty or hallucinated, fall back to raw
                if cleaned:
                    return cleaned
        except Exception:
            pass

        return raw_text
