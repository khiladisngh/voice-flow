# Contributing to Voice Flow

Thanks for taking the time to contribute. Voice Flow is a Linux/Wayland dictation
daemon, so most changes touch real audio devices, input devices, or the clipboard.
This guide covers how to get a working development environment and what a
mergeable pull request looks like.

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Prerequisites

- **Linux with a Wayland session.** Development happens on Fedora + KDE Plasma 6.
  X11 is not supported: injection relies on `wl-clipboard`.
- **Python 3.12 or newer.**
- **[uv](https://docs.astral.sh/uv/)** for dependency and environment management.
- **PipeWire** with `pw-record` on `PATH` (package `pipewire-utils` on Fedora,
  `pipewire-bin` on Debian/Ubuntu). Audio capture shells out to `pw-record`.
- **`wl-clipboard`**, providing `wl-copy` and `wl-paste`.
- **Membership of the `input` group**, so the daemon can read `/dev/input/event*`
  and open `/dev/uinput` without root:

  ```bash
  sudo usermod -aG input $USER
  ```

  Log out and back in for the new group to take effect. Verify with `id -nG`.

- **Optional: an NVIDIA GPU.** CUDA gives roughly an order of magnitude faster
  transcription. Without one, set `stt.compute_type` to a CPU-friendly value; the
  code paths are identical, just slower.
- **Optional: [Ollama](https://ollama.com/)** for LLM cleanup. Pull the model with
  `ollama pull qwen2.5:1.5b`. If Ollama is not running, set `cleaner.enabled` to
  `false` in `config.json` and raw transcripts are injected verbatim.

## Setup

```bash
git clone https://github.com/khiladisngh/voice-flow.git
cd voice-flow
uv sync --extra cuda --group dev
.venv/bin/pytest
```

`uv sync` creates `.venv/` in the repository root and installs the project in
editable mode. The `cuda` extra pulls the NVIDIA CUDA runtime wheels (~2.2 GB) —
omit it (`uv sync --group dev`) if you are working CPU-only or just editing docs
and tests. The `dev` group brings in `pytest`, `pytest-cov`, `ruff`, and
`bump-my-version`; the separate `docs` group (`uv sync --group docs`) brings in
`zensical`.

Note that the first transcription downloads the Whisper `large-v3-turbo` weights
(~1.6 GB) into the Hugging Face cache. That download is not part of `uv sync`.

## Tests

Full suite — run this before opening a pull request:

```bash
.venv/bin/pytest
```

CI runs the same command on hosted runners with no sound card, no GPU, and no
`/dev/uinput` — the suite is hermetic, so there is no separate CI subset and
there are no hardware markers.

**Any new test MUST NOT touch the real desktop session.** Patch the seam
instead. An earlier version of these tests constructed real `TextInjector`
objects, so `pytest` opened `/dev/uinput`, synthesized `Ctrl+V` into the focused
window, and overwrote the developer's clipboard. `tests/conftest.py` now
neutralises `evdev.UInput` and both clipboard helpers for the whole suite via an
autouse fixture, and `fake_pw_record` stands in for `pw-record`.

Verify your change kept the suite hermetic — the canary must survive:

```bash
printf 'CANARY' | wl-copy
.venv/bin/pytest -q >/dev/null 2>&1
test "$(wl-paste)" = CANARY && echo "session intact"
```

## Lint

```bash
.venv/bin/ruff check .
.venv/bin/ruff format .
```

CI runs `ruff check .` and `ruff format --check .`, so format before pushing.
Optionally install the git hooks from `.pre-commit-config.yaml` so this happens
automatically. `pre-commit` is not a project dependency; run it as a tool:

```bash
uvx pre-commit install
```

## Commits

- Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):
  `feat:`, `fix:`, `docs:`, `build:`, `refactor:`, `test:`, `chore:`. Append `!`
  or add a `BREAKING CHANGE:` footer for incompatible changes.
- **One logical change per pull request.** Split unrelated refactors out; they are
  much easier to review and to revert.
- **Add a changelog entry** under the `## [Unreleased]` heading in
  [`CHANGELOG.md`](CHANGELOG.md), in the appropriate `Added` / `Changed` /
  `Fixed` / `Removed` / `Security` subsection. Do not edit released sections and
  do not bump the version yourself — releases do that.
- Keep the description focused on _why_; the diff already shows _what_.

## Release

Maintainers only.

```bash
.venv/bin/bump-my-version bump patch   # or: minor | major
git push --follow-tags
```

`bump-my-version` rewrites the version in `pyproject.toml` and
`voice_flow/__init__.py`, inserts a dated `## [X.Y.Z] - YYYY-MM-DD` heading below
the `## [Unreleased]` anchor in `CHANGELOG.md` (so everything you accumulated
under `Unreleased` becomes that release), commits, and tags `vX.Y.Z`. Pushing the
tag triggers `.github/workflows/release.yml`, which extracts that changelog
section into the GitHub Release notes.

## Architecture

Before changing how the modules fit together, read
[`docs/architecture.md`](docs/architecture.md) — it covers the hotkey → capture →
transcribe → clean → inject pipeline, the Unix-socket IPC framing, and where
runtime artefacts live.
