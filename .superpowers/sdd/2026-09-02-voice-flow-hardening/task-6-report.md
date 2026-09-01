# Task 6 Report: Cleaner Connection Pooling & Prompt Sanitization

## Summary
Enhanced `TextCleaner` with HTTP connection pooling via a persistent `requests.Session()` to eliminate TCP handshake latency on repeated dictations to the local Ollama LLM endpoint, and implemented prompt sanitization wrapping user speech inside `<spoken_text>` tags to protect against prompt injection and boundary ambiguity.

## Changes Implemented

### 1. `voice_flow/cleaner.py`
- **Session Pooling**: Initialized `self.session = requests.Session()` in `TextCleaner.__init__` to reuse HTTP connections across multiple cleanup calls.
- **Graceful Resource Teardown**: Added `close()` method to cleanly close the underlying HTTP session.
- **Short-Circuit Hardening**: Handled empty, whitespace-only, `None`, and < 3-word inputs early without invoking the LLM.
- **Prompt Sanitization**: Updated prompt template to isolate user speech within XML-style delimiter tags:
  ```python
  prompt = f"{SYSTEM_PROMPT}\n\n<spoken_text>\n{raw_text}\n</spoken_text>\n\nClean Output:"
  ```
- **Connection Usage**: Replaced top-level `requests.post(...)` with `self.session.post(self.ollama_url, ...)`.
- **Fallback Integrity**: Maintained fallback to original `raw_text` on empty/whitespace LLM responses, HTTP errors (e.g. 500), or connection/network exceptions.

### 2. `tests/test_cleaner.py`
Created comprehensive unit test suite with 10 test cases:
1. `test_cleaner_initialization_has_session`: Verifies `self.session` is initialized as a `requests.Session`.
2. `test_clean_short_circuit_empty_and_short_text`: Verifies `None`, empty string, whitespace-only, and 1-2 word inputs return immediately without calling `session.post`.
3. `test_clean_prompt_wrapping_with_spoken_text_tags`: Verifies correct prompt template structure containing `<spoken_text>\n{raw_text}\n</spoken_text>` and payload arguments.
4. `test_clean_prompt_injection_containment`: Verifies adversarial or injection-style spoken inputs are strictly contained within `<spoken_text>` tags.
5. `test_clean_uses_session_post_not_requests_post`: Ensures `cleaner.clean()` calls `session.post` rather than the module-level `requests.post`.
6. `test_clean_empty_or_whitespace_llm_response_fallback`: Tests fallback when LLM response is empty or whitespace.
7. `test_clean_http_error_fallback`: Tests fallback when Ollama responds with non-200 HTTP status code.
8. `test_clean_exception_fallback`: Tests fallback when network errors or request exceptions occur.
9. `test_clean_session_persistence_across_multiple_calls`: Verifies session object persistence across multiple successive calls.
10. `test_cleaner_close`: Verifies `close()` properly invokes `session.close()`.

## Verification
Executed test suite using the project virtual environment:
```bash
/home/gishant-singh/Dev/tools/voice-flow/.venv/bin/pytest tests/test_cleaner.py
```

### Result
```
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/gishant-singh/Dev/tools/voice-flow
configfile: pyproject.toml
plugins: anyio-4.14.2
collected 10 items

tests/test_cleaner.py ..........                                         [100%]

============================== 10 passed in 0.06s ==============================
```

## Status
DONE
