# Troubleshooting

Start here:

```bash
./voice-flow.sh status
systemctl --user status voice-flow --no-pager
journalctl --user -u voice-flow -n 50 --no-pager
```

A healthy start-up log contains, in order:

```
[Daemon] Initializing Transcriber on cuda (large-v3-turbo)...
[Daemon] Connecting to Ollama cleaner (hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M)...
[Hotkey] Listening to keyboard: <your keyboard> (/dev/input/eventN)
[Hotkey] Active global combo: KEY_RIGHTCTRL + KEY_RIGHTALT
[Daemon] Voice Flow Daemon is warm and ready!
```

Any missing line tells you which stage to look at below.

## Quick reference

| Symptom                               | Likely cause                                                      | Fix                                                                                                                    |
| ------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Hotkey does nothing                   | Not in the `input` group, so `/dev/input` is unreadable           | `sudo usermod -aG input $USER`, then **log out and back in**; check the log for `[Hotkey] Listening to keyboard` lines |
| Paste inserts stale clipboard content | Clipboard restored before the target consumed the offer           | Raise the 350 ms restore delay in `voice_flow/injector.py`, or set `ui.restore_clipboard` to `false`                   |
| `libcublas.so.12 is not found`        | CUDA runtime wheels not installed                                 | `uv sync --extra cuda`                                                                                                 |
| No audio captured                     | `pw-record` missing, or the wrong default source                  | Install `pipewire-utils` / `pipewire-bin`; select the right input in your sound settings                               |
| Daemon fails to start                 | Wrong path in the unit, port/socket in use, or model load failure | `systemctl --user status voice-flow` and `journalctl --user -u voice-flow`                                             |
| Ollama unreachable                    | Server down or wrong `ollama_url`                                 | Start Ollama; cleanup silently falls back to the raw transcript, so dictation keeps working                            |
| Cleanup suddenly takes seconds        | Ollama offloaded part of the model to the CPU when the GPU filled | Check `ollama ps` and `nvidia-smi`; free VRAM, use the 0.8B model, or lower `cleaner.timeout_sec`                      |

## The hotkey does nothing

**Cause.** In almost every case the user is not in the `input` group, so
`evdev.list_devices()` returns nothing readable and the listener finds no
keyboards.

**Diagnose.** Look for these two lines in the log:

```bash
journalctl --user -u voice-flow | grep '^\[Hotkey\]'
```

If you see:

```
[Hotkey] No suitable keyboard devices found for global hotkeys.
```

then no device was readable. Confirm:

```bash
id -nG | tr ' ' '\n' | grep -x input || echo "NOT in input group"
```

**Fix.**

```bash
sudo usermod -aG input $USER
```

Then log out and back in. Group changes only apply to new login sessions, and the
systemd user manager that runs the daemon inherits its groups from the session —
`newgrp` in a terminal will not fix the service. After re-login:

```bash
systemctl --user restart voice-flow
journalctl --user -u voice-flow | grep '^\[Hotkey\]'
```

You should now get one `[Hotkey] Listening to keyboard: ...` line per physical
keyboard.

**Other causes.**

- **The combo resolved to nothing.** Check the
  `[Hotkey] Active global combo:` line. If it shows fewer keys than you
  configured, a name in `hotkey.combo` is misspelled — the resolver drops unknown
  names. See the [key-name reference](configuration.md#hotkey-key-names).
- **`hotkey.enabled` is `false`.** Then there is no listener at all, by design.
  Either set it back to `true` or bind a desktop shortcut as described in
  [Usage](usage.md#option-b-use-your-desktops-shortcut-system).
- **Keyboard plugged in after start-up.** It should be picked up within 5 seconds
  by the rescan; look for a `[Hotkey] Discovered and listening to keyboard:`
  line. If it never appears, the device does not expose any key from your combo.
- **The daemon is not running at all.** `./voice-flow.sh status` reporting
  `Daemon running: NO` means the hotkey cannot work; go to
  [the daemon section](#the-daemon-fails-to-start).

## The paste inserts stale clipboard content

**Symptom.** Instead of your dictation, the window receives whatever you had
copied before — or the dictated text appears once and is immediately replaced.

**Cause.** Wayland's clipboard is lazy. `wl-copy` advertises a data _offer_; the
receiving application fetches the bytes some time after it sees the `Ctrl+V`.
Voice Flow waits 350 ms and then restores your previous clipboard. Applications
that fetch slower than that — Electron apps, JetBrains IDEs, and terminals under
load are the usual suspects — read the restored contents instead.

**Fix (keep restore, wait longer).** The delay is a constant in
`voice_flow/injector.py`:

```python
# Wait 350ms to allow target Wayland client to complete data offer consumption
if self.restore_clipboard and old_clipboard is not None and success:
    time.sleep(0.35)
```

Raise `0.35` to `0.8` and restart the daemon. The cost is that your clipboard
stays overwritten for that much longer after each dictation.

**Fix (drop restore).** Simpler and always reliable — set in `config.json`:

```json
{ "ui": { "restore_clipboard": false } }
```

Dictated text is then left on the clipboard and nothing is restored, so there is
no race at all. Restart the daemon afterwards.

## `libcublas.so.12 is not found`

**Symptom.** The daemon dies during start-up, right after
`[Daemon] Initializing Transcriber on cuda (...)`, with a `ctranslate2` error
naming `libcublas.so.12` or `libcudnn`.

**Cause.** The CUDA runtime libraries are an optional extra, because
`nvidia-cublas-cu12` and `nvidia-cudnn-cu12` are about 2.2 GB installed. A plain
`uv sync` does not install them.

**Fix.**

```bash
uv sync --extra cuda
systemctl --user restart voice-flow
```

Verify:

```bash
.venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

Expected: `1` or higher.

**If it still fails.** `voice_flow/transcriber.py` loads the bundled shared
objects with `RTLD_GLOBAL` before importing `faster_whisper`, and looks for them
under `<sys.prefix>/lib/python3.X/site-packages/nvidia/{cublas,cudnn}/lib`. Check
they are there:

```bash
.venv/bin/python -c "
import sys, pathlib
sp = pathlib.Path(sys.prefix)/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'site-packages'
for d in ('cublas','cudnn'):
    p = sp/'nvidia'/d/'lib'
    print(p, p.exists(), len(list(p.glob('*.so*'))) if p.exists() else 0)
"
```

A `0` count means the wheels did not install. If you have no NVIDIA GPU, use the
CPU configuration instead:

```json
{ "stt": { "device": "cpu", "compute_type": "int8" } }
```

Also confirm the driver itself works — `nvidia-smi` must succeed for the user
running the daemon.

## No audio is captured

**Symptom.** The start notification appears, but nothing is pasted and the log
shows no transcription. `record-stop` exits silently.

**Cause.** `recorder.stop()` returns the WAV path only if the file exists and is
non-empty, so an empty capture is indistinguishable from "nothing recorded" and
the pipeline is skipped rather than fed silence.

**Diagnose.** Is `pw-record` installed?

```bash
command -v pw-record || echo "pw-record MISSING"
```

Can it record from your default source at all?

```bash
pw-record --channels 1 --rate 16000 /tmp/test.wav
# speak, then Ctrl-C
ls -l /tmp/test.wav && pw-play /tmp/test.wav
```

- **Missing binary** → install `pipewire-utils` (Fedora) or `pipewire-bin`
  (Debian/Ubuntu).
- **Zero-byte or silent file** → the default input source is wrong or muted.
  List sources and check the default:

  ```bash
  wpctl status
  ```

  Set the correct default in your desktop's sound settings, or with
  `wpctl set-default <id>`, then unmute and raise the input volume.

**Under systemd only.** If manual `pw-record` works but the daemon captures
nothing, the service cannot reach the PipeWire socket. The recorder exports
`PIPEWIRE_RUNTIME_DIR` automatically when `/run/user/<uid>/pipewire-0` exists, and
the shipped unit passes `XDG_RUNTIME_DIR` through `PassEnvironment`. Confirm the
socket exists:

```bash
ls -l /run/user/$(id -u)/pipewire-0
systemctl --user show voice-flow -p Environment -p PassEnvironment
```

Also check for a stale recording state blocking new captures:

```bash
ls -l "$XDG_RUNTIME_DIR/voice-flow/"
```

`recorder.pid` is cleaned up automatically when the process behind it is gone, so
a lingering file is harmless — but `record_current.wav` at 0 bytes confirms
`pw-record` started and produced nothing.

## The daemon fails to start

**Diagnose.**

```bash
systemctl --user status voice-flow --no-pager
journalctl --user -u voice-flow -n 80 --no-pager
```

Then run it in the foreground, where the traceback is unmissable:

```bash
systemctl --user stop voice-flow
./voice-flow.sh daemon
```

| Log evidence                                     | Cause                                                                | Fix                                                                                                                   |
| ------------------------------------------------ | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `Virtualenv not found at .../.venv/bin/python`   | Dependencies never synced, or the unit points at the wrong directory | `uv sync --extra cuda`; check `WorkingDirectory`/`ExecStart` in `~/.config/systemd/user/voice-flow.service`           |
| `status=203/EXEC` or `no such file or directory` | `voice-flow.sh` path wrong or not executable                         | Fix the unit paths, `chmod +x voice-flow.sh`, `systemctl --user daemon-reload`                                        |
| Stops after `Initializing Transcriber`           | CUDA or model problem                                                | See [`libcublas.so.12`](#libcublasso12-is-not-found)                                                                  |
| `Address already in use`                         | Another daemon owns the socket                                       | `systemctl --user stop voice-flow`, remove `$XDG_RUNTIME_DIR/voice-flow/daemon.sock` if it persists, then start again |
| `ValueError: unsupported compute type`           | `stt.device` and `stt.compute_type` mismatch                         | `int8` for CPU, `int8_float16` for CUDA                                                                               |
| Starts, then restarts every few seconds          | `Restart=on-failure` looping over a real crash                       | Read the traceback in the foreground run; the unit retries after `RestartSec=3`                                       |

The shipped unit uses `%h` and expects the checkout at `%h/Dev/tools/voice-flow`.
If you cloned elsewhere, edit both `WorkingDirectory` and `ExecStart`, then:

```bash
systemctl --user daemon-reload
systemctl --user restart voice-flow
```

**Socket present but not answering.** `./voice-flow.sh status` printing
`Daemon running: NO` while `daemon.sock` exists means a stale socket file from an
unclean exit. Restarting the daemon unlinks it — `start_server()` removes any
existing socket before binding.

## Ollama is unreachable

**Symptom.** Dictation works, but the pasted text keeps the "um"s and has no
punctuation. The `clean_ms` figure is near zero.

**Cause.** By design, cleanup fails open: any error — connection refused, non-200
status, timeout, empty response — returns the raw transcript. You never lose
words to a broken cleaner, which also means the failure is silent.

**Diagnose.**

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:11434/api/tags
ollama list | grep Qwen3.5-2B
```

Test the exact endpoint the daemon uses:

```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M","think":false,"prompt":"say ok","stream":false}' | head -c 200
```

**Fix.**

- **Server down** → `systemctl --user start ollama` (or `systemctl start ollama`,
  depending on how you installed it).
- **Model not pulled** → `ollama pull hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M`.
- **Different host or port** → correct `cleaner.ollama_url` in `config.json`. It
  must be the full generate URL, including `/api/generate`.
- **Consistently slower than 15 seconds** → the client timeout is exceeded and the
  raw text is used. Switch to a smaller model, or set `cleaner.enabled` to
  `false` and accept raw transcripts.
- **Transcript longer than 500 words** → cleanup intentionally pastes the raw
  transcript without calling Ollama. The journal logs
  `[Cleaner] Transcript is N words (limit 500); pasting raw transcript`.

Check the daemon's own view at start-up: with cleanup enabled the log contains
`[Daemon] Connecting to Ollama cleaner (hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M)...`. If that line is
absent, `cleaner.enabled` is `false` in your config and no cleanup was ever
attempted.

## Cleanup suddenly takes seconds

**Symptom.** Dictation pauses for several seconds after transcription, and the
journal reports a large `clean_ms` value.

**Cause.** When the GPU is full, Ollama offloads part of the cleanup model to
the CPU. The request still succeeds, but CPU inference stalls the paste.

**Diagnose.**

```bash
ollama ps
nvidia-smi
```

The `PROCESSOR` column in `ollama ps` shows a CPU/GPU split when the model has
spilled. `nvidia-smi` shows which processes are consuming the card.

**Fix.**

- Free VRAM used by other GPU applications.
- Switch `cleaner.model` to
  `hf.co/unsloth/Qwen3.5-0.8B-GGUF:Q8_0`.
- Lower `cleaner.timeout_sec` so a spilled cleanup fails open to the raw
  transcript quickly instead of stalling the paste.

## Text goes to the wrong window

The paste lands in whatever has keyboard focus when processing _completes_, not
when you started speaking. Stay in the target window for the ~420 ms after you
release the hotkey.

If nothing is pasted anywhere and the log shows a transcript, the `uinput` device
could not be created — `paste()` returns `False` in that case. Confirm write
access:

```bash
test -w /dev/uinput && echo writable || echo "NOT writable"
```

If it is not writable, configure the persistent udev rule and ensure the module is loaded:

```bash
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/99-uinput.rules
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
sudo modprobe uinput
sudo udevadm control --reload-rules && sudo udevadm trigger /dev/uinput
```

Also make sure your user is a member of the `input` group (`id -nG | grep -w input`).

## Nothing above matches

Collect the evidence and open an issue:

```bash
./voice-flow.sh status
journalctl --user -u voice-flow -n 100 --no-pager
.venv/bin/python -c "import voice_flow; print(voice_flow.__version__)"
uv --version && python3 --version
```

Report it at
[github.com/khiladisngh/voice-flow/issues](https://github.com/khiladisngh/voice-flow/issues),
including your `config.json` and whether the same behaviour occurs with
`./voice-flow.sh daemon` in the foreground.

Next: [Development](development.md).
