# Configuration

All settings live in a single `config.json` at the repository root, next to the
`voice_flow/` package. It is read once at process start-up, so restart the daemon
after editing:

```bash
systemctl --user restart voice-flow
```

Every key is optional. A missing key — or a missing or unparseable
`config.json` — falls back to the default shown below, so a partial file is
valid. There is no schema validation: an unrecognised key is ignored, and an
invalid value surfaces as an error from the component that consumes it.

## Full default file

```json
{
  "hotkey": {
    "enabled": true,
    "combo": ["KEY_RIGHTCTRL", "KEY_RIGHTALT"],
    "hold_threshold_sec": 0.45
  },
  "stt": {
    "model_size": "large-v3-turbo",
    "device": "cuda",
    "compute_type": "int8_float16",
    "language": null
  },
  "cleaner": {
    "enabled": true,
    "ollama_url": "http://localhost:11434/api/generate",
    "model": "hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M",
    "temperature": 0.1,
    "timeout_sec": 15.0,
    "keep_alive": -1,
    "options": {}
  },
  "audio": {
    "sample_rate": 16000,
    "channels": 1,
    "temp_file": "auto"
  },
  "ui": {
    "sound_feedback": true,
    "notifications": true,
    "restore_clipboard": true
  }
}
```

## `hotkey`

Controls the built-in kernel-level listener. Applies to the daemon only; the CLI
subcommands do not read it.

| Key                         | Type             | Default                             | Effect                                                                                                                                                                                              |
| --------------------------- | ---------------- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hotkey.enabled`            | boolean          | `true`                              | Whether the daemon opens `/dev/input` and listens for the combo. Set to `false` to bind a shortcut through your desktop instead — the daemon still holds the model warm and serves the socket.      |
| `hotkey.combo`              | array of strings | `["KEY_RIGHTCTRL", "KEY_RIGHTALT"]` | The `evdev` key names that must all be held down simultaneously to trigger. Names that do not exist in `evdev.ecodes` are silently dropped, so a typo weakens the combo rather than raising.        |
| `hotkey.hold_threshold_sec` | number (seconds) | `0.45`                              | The push-to-talk / toggle boundary. Releasing the combo after at least this long stops recording immediately (push-to-talk); releasing sooner leaves recording running until the next tap (toggle). |

!!! warning "An empty combo triggers on nothing"
`combo` is resolved against `evdev.ecodes` at start-up. If every entry is
misspelled the required set is empty and no key event can ever satisfy it.
Check the `[Hotkey] Active global combo:` line in the log to see what was
actually resolved.

Raising `hold_threshold_sec` (for example to `0.7`) makes toggling easier if you
tend to linger on the keys; lowering it to `0.25` makes push-to-talk more
responsive to short bursts.

### Hotkey key names

`combo` takes raw Linux input event names, exactly as spelled in
`evdev.ecodes`. They are case-sensitive and always prefixed with `KEY_`.

| Purpose           | Names                                                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Modifiers, right  | `KEY_RIGHTCTRL`, `KEY_RIGHTALT`, `KEY_RIGHTSHIFT`, `KEY_RIGHTMETA`                                                                   |
| Modifiers, left   | `KEY_LEFTCTRL`, `KEY_LEFTALT`, `KEY_LEFTSHIFT`, `KEY_LEFTMETA`                                                                       |
| Function keys     | `KEY_F1` … `KEY_F12` (for example `KEY_F8`)                                                                                          |
| Letters           | `KEY_A` … `KEY_Z`                                                                                                                    |
| Digits            | `KEY_0` … `KEY_9`                                                                                                                    |
| Other useful keys | `KEY_SPACE`, `KEY_ENTER`, `KEY_TAB`, `KEY_ESC`, `KEY_CAPSLOCK`, `KEY_SCROLLLOCK`, `KEY_PAUSE`, `KEY_INSERT`, `KEY_MENU`, `KEY_GRAVE` |

To list every name your `evdev` build knows:

```bash
.venv/bin/python -c "from evdev import ecodes; print('\n'.join(sorted(n for n in dir(ecodes) if n.startswith('KEY_'))))"
```

To find the name of a specific physical key, read raw events while pressing it:

```bash
sudo .venv/bin/python -c "
import evdev
d = evdev.InputDevice('/dev/input/event3')
for e in d.read_loop():
    if e.type == evdev.ecodes.EV_KEY and e.value == 1:
        print(evdev.ecodes.KEY[e.code])
"
```

Replace `event3` with your keyboard. To find it, either read the
`[Hotkey] Listening to keyboard: <name> (<path>)` lines from the daemon log, or
list the devices `evdev` can see:

```bash
.venv/bin/python -c "
import evdev
for p in evdev.list_devices():
    d = evdev.InputDevice(p)
    print(p, d.name)
"
```

Examples:

```json
{ "hotkey": { "combo": ["KEY_F8"] } }
```

```json
{ "hotkey": { "combo": ["KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_SPACE"] } }
```

A single-key combo works, but pick something you never type — a bare `KEY_A`
would start dictation every time you write the letter, because the listener sees
kernel events regardless of which application has focus.

## `stt`

Speech-to-text via [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
on CTranslate2.

| Key                | Type           | Default            | Effect                                                                                                                                                                                        |
| ------------------ | -------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `stt.model_size`   | string         | `"large-v3-turbo"` | Whisper model to load. Accepts any faster-whisper size name or a local model directory. Larger is more accurate, slower, and heavier in VRAM.                                                 |
| `stt.device`       | string         | `"cuda"`           | Inference device: `"cuda"`, `"cpu"`, or `"auto"`.                                                                                                                                             |
| `stt.compute_type` | string         | `"int8_float16"`   | CTranslate2 quantisation. Must be compatible with `device` — `int8_float16` and `float16` are CUDA-only.                                                                                      |
| `stt.language`     | string or null | `null`             | ISO 639-1 code (`"en"`, `"de"`, `"fr"`, …). `null` auto-detects per utterance, which costs a little latency; pinning it is both faster and more reliable if you only dictate in one language. |

Fixed decoding parameters, not exposed in `config.json`: greedy decoding
(`beam_size=1`) for latency, Silero VAD filtering with a 500 ms minimum silence
duration to trim dead air, and a punctuation-priming `initial_prompt` so short
utterances come back capitalised and punctuated.

### Model trade-offs

| `model_size`           | Approx. VRAM (`int8_float16`) | Accuracy  | Notes                                                                                   |
| ---------------------- | ----------------------------- | --------- | --------------------------------------------------------------------------------------- |
| `tiny` / `tiny.en`     | ~0.1 GB                       | Poor      | Usable for single words and commands only.                                              |
| `base` / `base.en`     | ~0.2 GB                       | Fair      | Fastest option that produces readable sentences.                                        |
| `small` / `small.en`   | ~0.5 GB                       | Good      | Reasonable choice for CPU-only setups.                                                  |
| `medium` / `medium.en` | ~1.5 GB                       | Very good | Slower than `large-v3-turbo` with no accuracy benefit — skip it.                        |
| **`large-v3-turbo`**   | **~1.1 GB (measured)**        | Excellent | **Default.** ~360 ms per short utterance on an RTX 3070. Best accuracy-per-millisecond. |
| `large-v3`             | ~3 GB                         | Excellent | Marginally better on hard audio, several times slower.                                  |

Only the `large-v3-turbo` row is measured on this project's reference hardware
(RTX 3070); the others are approximate and will vary with audio length and
driver version. The `.en` variants are English-only and slightly more accurate
for English at the same size — pair them with `"language": "en"`.

### Compute-type trade-offs

| `compute_type` | Valid on     | Relative VRAM      | Notes                                                                                                                |
| -------------- | ------------ | ------------------ | -------------------------------------------------------------------------------------------------------------------- |
| `int8_float16` | CUDA         | Lowest             | **Default.** INT8 weights with FP16 compute. Best latency/VRAM point with no perceptible quality loss for dictation. |
| `float16`      | CUDA         | ~2× `int8_float16` | Reference GPU quality. Choose it only if you can hear a difference.                                                  |
| `int8`         | CPU and CUDA | Lowest             | The correct choice for `"device": "cpu"`.                                                                            |
| `float32`      | CPU and CUDA | Highest            | Slow everywhere. No reason to use it here.                                                                           |
| `auto`         | Both         | —                  | Lets CTranslate2 pick the fastest type the device supports.                                                          |

!!! warning "Mismatched device and compute type"
`"device": "cpu"` with `"compute_type": "int8_float16"` fails at model load.
Use `int8` on the CPU.

## `cleaner`

LLM post-processing through a local [Ollama](https://ollama.com/) server. The
transcript is wrapped in `<spoken_text>` delimiters before being sent, so speech
containing instruction-like phrasing cannot rewrite the system prompt.

| Key                   | Type    | Default                                  | Effect                                                                                                                                                                                                                                        |
| --------------------- | ------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cleaner.enabled`     | boolean | `true`                                   | Whether to post-process at all. `false` pastes the raw Whisper transcript and skips the Ollama connection entirely.                                                                                                                           |
| `cleaner.ollama_url`  | string  | `"http://localhost:11434/api/generate"`  | Full URL of Ollama's generate endpoint. Point it at another host to use a remote server — note that doing so sends transcripts over the network and breaks the offline guarantee.                                                             |
| `cleaner.model`       | string  | `"hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M"` | Any Ollama model name, including `hf.co/<repo>:<quant>` GGUF pulls. Must already be pulled (`ollama pull <name>`). Thinking-capable models are handled automatically (`think` is disabled per request). Restart the daemon after changing it. |
| `cleaner.temperature` | number  | `0.1`                                    | Sampling temperature. Keep it low; cleanup is a rewriting task, and higher values invent words.                                                                                                                                               |
| `cleaner.timeout_sec` | number  | `15.0`                                   | Client timeout per request. Slower than this and the raw transcript is pasted, so a stalled Ollama never blocks dictation.                                                                                                                    |
| `cleaner.keep_alive`  | int/str | `-1`                                     | Ollama `keep_alive`; `-1` pins the model in VRAM so the first dictation after an idle gap does not pay a reload.                                                                                                                              |
| `cleaner.options`     | object  | `{}`                                     | Extra Ollama `options` merged over the defaults, for per-model tuning. On an 8 GB GPU shared with Whisper, `{"num_gpu": 999}` forces full offload of the 2B model (≈0.35 s instead of ≈1.4 s when Ollama's estimate leaves 15 % on the CPU).  |

### Model choices

Measured on an RTX 3070 (8 GB) with Whisper `large-v3-turbo` resident and a desktop session open:

| Model                                  | VRAM    | Latency (p50)                                      | Notes                                                                                                                                       |
| -------------------------------------- | ------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M` | ≈2.3 GB | 0.2–0.4 s with `num_gpu: 999`; 1.0–1.4 s otherwise | Default. Best cleanup for English and code-heavy dictation; keeps Hindi, Hinglish and European languages when Whisper reports the language. |
| `hf.co/unsloth/Qwen3.5-0.8B-GGUF:Q8_0` | ≈1.4 GB | ≈0.2 s                                             | Low-VRAM option. Never switches language but leaves some fillers behind.                                                                    |
| `qwen2.5:1.5b` (previous default)      | ≈1.3 GB | ≈0.2 s                                             | English only in practice: translates Hindi/Hinglish to English and sometimes answers the dictation instead of rewriting it.                 |

Behaviour that is fixed in code rather than configurable:

- **Language steering.** Whisper's detected language is named in the prompt ("The spoken text is in Hindi…"), which is what keeps small models from translating.
- **Thinking disabled.** Every request sends `think: false`; a leaked `<think>` block is stripped from the response as a fail-safe.
- **Silent fallback.** Any failure — connection refused, non-200 status, empty response — returns the raw transcript. Cleanup can never lose your words.
- **Short-input bypass.** Text of fewer than three words skips the LLM entirely.
- **Long-transcript bypass.** Transcripts longer than 500 words skip the LLM and paste raw, because the prompt plus generation would exceed the 4096-token context window and the model would silently clean a truncated transcript.
- **Adaptive output cap.** `num_predict` is `max(128, word_count * 3)`; `num_ctx` is fixed at 4096.
- **Persistent HTTP session.** Connections are reused across utterances.

## `audio`

Capture through PipeWire's `pw-record`.

| Key                 | Type         | Default  | Effect                                                                                                                                                        |
| ------------------- | ------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `audio.sample_rate` | integer (Hz) | `16000`  | Recording sample rate, passed to `pw-record --rate`. Whisper resamples internally to 16 kHz, so a higher value costs disk and CPU without improving accuracy. |
| `audio.channels`    | integer      | `1`      | Channel count, passed to `pw-record --channels`. Mono is correct for speech.                                                                                  |
| `audio.temp_file`   | string       | `"auto"` | Where the WAV is written. `"auto"` uses `$XDG_RUNTIME_DIR/voice-flow/record_current.wav`, created at mode `0700`. An explicit absolute path overrides that.   |

!!! warning "Leave `temp_file` on `auto`"
`"auto"` keeps recordings in your per-user runtime directory, which is
tmpfs-backed, private at mode `0700`, and cleared at logout. An explicit path
somewhere world-readable such as `/dev/shm` or `/tmp` means any local user
can read your dictation audio.

## `ui`

Feedback and clipboard behaviour.

| Key                    | Type    | Default | Effect                                                                                                                                                                                                                                            |
| ---------------------- | ------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ui.sound_feedback`    | boolean | `true`  | Play a freedesktop sound through `pw-play` on record start and stop. Silently does nothing if no sound theme is installed.                                                                                                                        |
| `ui.notifications`     | boolean | `true`  | Send transient desktop notifications via `notify-send` ("Listening...", "Processing speech...").                                                                                                                                                  |
| `ui.restore_clipboard` | boolean | `true`  | Read the clipboard before pasting and put it back roughly 350 ms afterwards, so dictating does not destroy whatever you had copied. Set to `false` if the delay races with your applications, or if you want dictated text left on the clipboard. |

The restore delay exists because Wayland's clipboard hands over data lazily: the
receiving application fetches the offer some time after the paste keystroke. If
the previous contents are put back too early, the target pastes the _old_ text.
See [Troubleshooting](troubleshooting.md) if you hit that.

Next: [Architecture](architecture.md).

### `cleaner.keep_alive`

How long Ollama keeps the cleanup model in VRAM. Default `-1` pins it
indefinitely, so no dictation ever pays a model reload; the default
Qwen3.5-2B Q4_K_M model costs ~2.3 GiB of VRAM permanently. Ollama's own
default is 5 minutes of idle, after which the first dictation pays a reload of
~1.8 s warm, or up to ~13 s cold from disk. Set `"5m"` to reclaim ~2.3 GiB
when idle and accept that latency.

### `cleaner.timeout_sec`

Upper bound on a single cleanup request, default `15.0`. It must exceed a cold
model load, otherwise the first dictation after a pause silently falls back to
the raw transcript. Every fallback is logged.
