# Security Policy

## Supported Versions

Only the latest `0.1.x` release line receives security fixes. Voice Flow is
pre-1.0: fixes ship forward, not as backports to older tags.

| Version        | Supported          |
| -------------- | ------------------ |
| latest `0.1.x` | Yes                |
| anything older | No — upgrade first |

## Reporting a Vulnerability

**Do not open a public GitHub issue for a security problem.**

Report it privately through GitHub Security Advisories:

<https://github.com/khiladisngh/voice-flow/security/advisories/new>

Useful details to include:

- affected version (`voice_flow.__version__`, or the tag you installed),
- your distribution, kernel, and Wayland compositor,
- a minimal reproduction, and
- the impact you believe the issue has.

You can expect a first response **within 7 days**. Once a fix is ready it is
released in a new `0.1.x` version, and the advisory is published with credit to
the reporter unless you ask to remain anonymous.

## Threat Model

Voice Flow is a privileged local daemon. Understanding what it touches matters
more than any single bug:

- **It reads all keyboard input.** The hotkey listener opens `/dev/input/event*`
  via `evdev` and receives every key event from the monitored keyboards — not
  only the `Right Ctrl + Right Alt` combination it acts on. This is the same
  level of access a keylogger has. It is required because Wayland offers no
  portable global-hotkey API. Membership of the `input` group is what grants it;
  grant that membership deliberately.
- **It writes synthetic keystrokes.** Injection opens `/dev/uinput` and keeps a
  persistent virtual keyboard, which it uses to send `Ctrl+V` to whichever window
  currently has focus. Anything that can influence the injected text can type
  into your active application, including a terminal.
- **Recorded audio is stored on disk, briefly.** WAV captures, the PID file, and
  the IPC socket live in `$XDG_RUNTIME_DIR/voice-flow`, created with mode `0700`
  so only your user can read them. `$XDG_RUNTIME_DIR` is a per-user tmpfs that
  the session manager clears on logout, so recordings do not survive a reboot and
  are never written to `/tmp` or `/dev/shm`.
- **Transcripts go only to a local Ollama endpoint.** Cleanup posts text to
  `cleaner.ollama_url`, which defaults to
  `http://localhost:11434/api/generate`. Speech recognition runs entirely
  in-process via `faster-whisper`. **There is no network egress by default** — no
  telemetry, no cloud API, no crash reporting. Pointing `cleaner.ollama_url` at a
  non-local host sends your transcripts off the machine; that is a configuration
  decision, not a default.
- **Dictated speech is untrusted input to the LLM.** Transcripts are wrapped in
  `<spoken_text>` delimiters before reaching the cleanup model so that spoken
  words cannot easily be read as instructions. Prompt injection through a
  microphone remains a real, if awkward, attack surface: anything that can speak
  near your microphone can influence the injected text.
- **Out of scope.** A machine where another local process already runs as your
  user, or as root, is outside this threat model — such a process can read the
  input devices and the runtime directory directly, with or without Voice Flow.
