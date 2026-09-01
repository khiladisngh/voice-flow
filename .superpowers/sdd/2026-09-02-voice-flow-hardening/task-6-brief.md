# Task 6: Cleaner Connection Pooling & Prompt Sanitization

## Objective
Enhance `TextCleaner` with connection pooling using a persistent `requests.Session()` to avoid TCP handshake overhead on every dictation, and isolate user speech within `<spoken_text>` tags to prevent prompt injection.

## Files to touch
- Modify: `voice_flow/cleaner.py`
- Test: `tests/test_cleaner.py`

## Requirements
1. In `voice_flow/cleaner.py`:
   - Initialize `self.session = requests.Session()` in `__init__`.
   - Update `clean(raw_text: str) -> str`:
     - If raw_text is empty or whitespace or < 3 words, return immediately.
     - Wrap input in prompt:
       `f"{SYSTEM_PROMPT}\n\n<spoken_text>\n{raw_text}\n</spoken_text>\n\nClean Output:"`
     - Use `self.session.post(...)`.
     - Return cleaned output if non-empty, otherwise fallback to `raw_text`.
2. Write unit tests in `tests/test_cleaner.py`:
   - Verify session presence.
   - Verify short text short-circuit.
   - Test mocking responses and prompt structuring.
   - Run tests with `/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_cleaner.py`.
   - Commit with git.
