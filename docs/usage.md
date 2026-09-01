# Usage

With the daemon running, dictation is a single shortcut. Everything else on this
page is for scripting, custom keybindings, and diagnostics.

## The hotkey

The default combo is **Right Ctrl + Right Alt**. The daemon's `evdev` listener
watches for the whole combo going down and then coming back up, and decides what
to do from how long you held it. The boundary is
`hotkey.hold_threshold_sec`, `0.45` seconds by default.

| Gesture                                         | Behaviour                                                           |
| ----------------------------------------------- | ------------------------------------------------------------------- |
| **Hold** the combo for ≥ 0.45 s, speak, release | Push-to-talk. Recording starts on press and stops on release.       |
| **Tap** the combo (< 0.45 s)                    | Toggle on. Recording starts and keeps running with your hands free. |
| **Tap** again                                   | Toggle off. Recording stops and the transcript is pasted.           |

Both gestures share one shortcut, so there is nothing to choose up front: press
and hold for a short phrase, or tap for a long one and tap again when you are
done.

Recording start plays a soft sound and shows a "🎙️ Voice Flow — Listening..."
notification; stopping plays a second sound and shows "⚡ Voice Flow —
Processing speech...". Both are controlled by `ui.sound_feedback` and
`ui.notifications`.

When processing finishes, the cleaned text is put on the clipboard and a
synthetic `Ctrl+V` is sent to the focused window. Your previous clipboard
contents are restored about 350 ms later unless `ui.restore_clipboard` is
`false`.

!!! tip "Keep focus where you want the text"
The paste lands in whatever window has keyboard focus at the moment
processing completes — not the window that had focus when you started
speaking. Do not click away while the daemon is transcribing.

## Command line

The launcher script `./voice-flow.sh` runs the package from the project
virtualenv. If you installed the distribution, the console script `voice-flow`
is equivalent. With no argument, `toggle` is assumed.

| Command                                                        | What it does                                                                                                                                              |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `voice-flow toggle`                                            | Start recording if idle; otherwise stop, transcribe, clean, and paste. This is the scriptable equivalent of the hotkey.                                   |
| `voice-flow record-start`                                      | Start recording and return immediately. Does not transcribe.                                                                                              |
| `voice-flow record-stop`                                       | Stop recording, then transcribe, clean, and paste.                                                                                                        |
| `voice-flow daemon`                                            | Run the daemon in the foreground: loads Whisper, connects to Ollama, starts the hotkey listener, and serves the Unix socket. Normally started by systemd. |
| `voice-flow status` (or `./voice-flow.sh status` from a clone) | Report whether the daemon is answering on its socket and whether a recording is currently active.                                                         |

Anything else prints the usage line:

```
Usage: voice-flow [toggle|record-start|record-stop|daemon|status]
```

### `toggle`

```bash
./voice-flow.sh toggle
```

While idle, this starts `pw-record` and prints:

```
Listening... (Press hotkey again to finish & paste)
```

Run it again to finish. The audio path is handed to the warm daemon over the
Unix socket, which does the transcription with the model already in VRAM and
reports the round trip:

```
Pasted: Refactor the recorder to use the runtime directory. (198.4ms)
```

If the daemon is not reachable, the same process falls back to loading the model
itself. The dictation still works, it is just slow — expect several seconds of
model load:

```
Daemon not running, processing standalone...
Pasted: Refactor the recorder to use the runtime directory.
```

### `record-start` and `record-stop`

Use these when you want to drive capture from two separate key bindings or from a
script, rather than toggling from a single one.

```bash
./voice-flow.sh record-start
# ... speak ...
./voice-flow.sh record-stop
```

`record-stop` prefers the warm daemon exactly like `toggle` and falls back to
standalone processing if the socket is not answering. If nothing was captured —
no recording in progress, or a zero-byte WAV — it exits quietly without pasting.

### `status`

```bash
./voice-flow.sh status
```

```
Daemon running: YES (warm in GPU)
Recording active: False
```

`Daemon running` is a real `ping`/`pong` round trip on the Unix socket with a
1-second timeout, not a process-table guess. `Recording active` reflects whether
the PID in `$XDG_RUNTIME_DIR/voice-flow/recorder.pid` is a live process.

### `daemon`

```bash
./voice-flow.sh daemon
```

Runs in the foreground with logs on stdout — the fastest way to see what the
hotkey listener is actually binding to. Stop the systemd unit first, since only
one process can own the socket:

```bash
systemctl --user stop voice-flow
./voice-flow.sh daemon
```

`SIGINT` and `SIGTERM` are handled: the listener stops, the socket file is
removed, and the process exits cleanly.

## Managing the service

```bash
systemctl --user status voice-flow --no-pager   # is it up?
systemctl --user restart voice-flow             # reload config.json
systemctl --user stop voice-flow                # free the GPU
journalctl --user -u voice-flow -f              # live logs
```

!!! note "Configuration is read at start-up"
`config.json` is loaded once when the process starts. Restart the unit after
editing it.

## Binding a different shortcut

Voice Flow's built-in listener is a kernel-level `evdev` reader, which is why it
works inside applications that grab compositor shortcuts. There are two ways to
change the trigger.

### Option A: change the built-in combo

Edit `hotkey.combo` in `config.json` using `evdev` key names and restart:

```json
{
  "hotkey": {
    "enabled": true,
    "combo": ["KEY_RIGHTCTRL", "KEY_RIGHTALT"],
    "hold_threshold_sec": 0.45
  }
}
```

The full key-name reference is in
[Configuration](configuration.md#hotkey-key-names).

### Option B: use your desktop's shortcut system

If you would rather have KDE, GNOME, or your compositor own the binding, turn
the built-in listener off first so the two cannot both fire:

```json
{
  "hotkey": {
    "enabled": false
  }
}
```

Restart the daemon. It still loads the model, holds it warm, and serves the
socket — it simply stops reading `/dev/input`. Then bind a key to
`/path/to/voice-flow/voice-flow.sh toggle`.

In **KDE Plasma 6**:

1. Open **System Settings → Keyboard → Shortcuts**.
2. Click **Add New → Command or Script**.
3. Enter the absolute path to the launcher with the subcommand, for example
   `/home/you/voice-flow/voice-flow.sh toggle`.
4. Click the shortcut button next to the new entry and press your key
   combination.
5. Click **Apply**.

Because the daemon is still warm, the shortcut path has the same ~420 ms latency
as the built-in hotkey — the CLI only ships the audio path over the socket.

!!! warning "Compositor shortcuts are not global"
Desktop-level shortcuts are delivered by the compositor, so applications that
take an exclusive keyboard grab (some remote-desktop clients, virtual
machines, and full-screen games) will swallow them. The built-in `evdev`
listener is not affected. If you need dictation inside those applications,
keep `hotkey.enabled` set to `true`.

Next: [Configuration](configuration.md).
