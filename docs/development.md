# Development

This page covers working on Voice Flow itself. For the user-facing setup, see
[Installation](installation.md).

## Setup

```bash
git clone https://github.com/khiladisngh/voice-flow.git
cd voice-flow
uv sync --extra cuda --group dev
.venv/bin/pytest
```

Expected: `51 passed`.

The `cuda` extra is optional here too — see the
[CPU-only fallback](installation.md#cpu-only-fallback). The suite passes either
way, because nothing in it loads a Whisper model.

## Repository layout

| Path                        | Responsibility                                                                                           |
| --------------------------- | -------------------------------------------------------------------------------------------------------- |
| `voice_flow/paths.py`       | Runtime-artefact paths; the only place `$XDG_RUNTIME_DIR/voice-flow` and its `0700` mode are constructed |
| `voice_flow/recorder.py`    | `pw-record` subprocess supervision, PID file, notifications, sounds                                      |
| `voice_flow/transcriber.py` | `faster-whisper` wrapper with the load-bearing CUDA `dlopen` ordering                                    |
| `voice_flow/cleaner.py`     | Ollama post-processing with fail-open fallback                                                           |
| `voice_flow/injector.py`    | `wl-copy` + persistent `uinput` paste, clipboard restore                                                 |
| `voice_flow/hotkey.py`      | `evdev` global combo listener, hold-vs-tap logic, hot-plug rescan                                        |
| `voice_flow/daemon.py`      | Pipeline composition and the newline-delimited-JSON Unix socket server                                   |
| `voice_flow/main.py`        | CLI dispatch, daemon-first with standalone fallback, config loading                                      |
| `config.json`               | User configuration, read at daemon start-up                                                              |
| `voice-flow.sh`             | Launcher that runs the package from `.venv`                                                              |
| `voice-flow.service`        | systemd user unit; uses `%h`, never an absolute home path                                                |
| `tests/`                    | pytest suite plus `conftest.py` capability probes                                                        |
| `docs/`                     | This Zensical site                                                                                       |
| `plans/`                    | Retained engineering plans; outside `docs/`, so never published                                          |
| `mkdocs.yml`                | Site config, read by Zensical                                                                            |
| `Makefile`                  | CLI parity with the VS Code workspace tasks                                                              |
| `voice-flow.code-workspace` | Multi-root workspace: settings, extensions, tasks, launch configs                                        |
| `.github/workflows/`        | `ci.yml` (lint + test matrix), `docs.yml` (Pages deploy), `release.yml` (tag-triggered)                  |

See [Architecture](architecture.md) for what each module actually does and why.

## Tests

```bash
.venv/bin/pytest                           # everything: 51 passed
.venv/bin/pytest tests/test_hotkey.py -v   # one file
.venv/bin/pytest --cov=voice_flow          # coverage
```

There is no "CI subset" and there are no hardware markers: CI runs exactly the
command you run. Coverage is configured for `source = ["voice_flow"]` with
`voice_flow/transcriber.py` omitted — it cannot be exercised without a GPU and a
1.6 GB model download.

### The suite is hermetic, and must stay that way

Every test runs without a GPU, a PipeWire session, `/dev/uinput`, or a Wayland
compositor, which is why the same command is green on a CI runner and on a
developer machine.

This is not a nicety. An earlier version of these tests constructed real
`TextInjector` objects, so running `pytest` opened `/dev/uinput`, synthesized
real `Ctrl+V` keystrokes into whatever window happened to have focus, and
overwrote the developer's clipboard. Recorder tests spawned real `pw-record`
and opened the microphone.

`tests/conftest.py` installs an autouse fixture that neutralises those seams
for the whole suite:

| Seam                                   | Replaced with                        |
| -------------------------------------- | ------------------------------------ |
| `voice_flow.injector.evdev.UInput`     | A fresh `MagicMock` per construction |
| `TextInjector._set_clipboard`          | A mock; `wl-copy` never runs         |
| `TextInjector._get_current_clipboard`  | A mock returning `None`              |
| `voice_flow.recorder.subprocess.Popen` | `fake_pw_record`, per-test opt-in    |

`fake_pw_record` writes a real WAV with the `wave` module and spawns a harmless
`sleep` so the PID is genuinely signalable — that keeps the `stop()` teardown
path (SIGINT, the wait loop, the `SIGKILL` escalation) under test without ever
touching audio hardware.

!!! warning "Never let a test reach the real session"

    A new test must not open `/dev/uinput`, synthesize a keystroke, write the
    clipboard, or spawn `pw-record`. Patch the seam instead. Verify with a
    clipboard canary, which must survive the suite untouched:

    ```bash
    printf 'CANARY' | wl-copy
    .venv/bin/pytest -q >/dev/null 2>&1
    test "$(wl-paste)" = CANARY && echo "session intact"
    ```

`--strict-markers` is enabled, so a typo in a marker name is a collection error
rather than a silently ignored decorator.

### Reproducing the published benchmarks

```bash
.venv/bin/python scripts/benchmark.py
```

It synthesizes speech with `espeak-ng`, runs it through the real transcriber
and cleaner, and prints medians over warm runs plus RSS/PSS from
`/proc/<pid>/smaps_rollup`. Every figure in the README comes from this script.

### Evaluating a cleaner model

Before changing `cleaner.model`, run the probe against the candidate. It uses the
real prompt and a fixed set of English, Hindi, Hinglish and German dictations, and
prints latency plus the output so you can see whether the model translates,
answers, or leaves fillers behind:

```bash
.venv/bin/python scripts/cleaner_probe.py hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M --num-gpu 999
```

### Test-writing conventions

- **Isolate the runtime directory.** Every test that touches paths sets
  `monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))`. Never let a test write
  into the real runtime directory — it would fight the running daemon.
- **Do not mock what you are asserting.** `tests/test_cleaner.py` patches
  `cleaner.session.post` and then asserts on the prompt that was actually built,
  including the `<spoken_text>` delimiters, rather than trusting a stubbed return.
- **Prefer real sockets over mocked ones.** `tests/test_ipc.py` binds an actual
  `AF_UNIX` socket in `tmp_path` and exercises the newline framing end to end,
  including empty responses and large payloads.
- **Assert the failure paths.** Fail-open behaviour (cleaner fallback, stale PID
  recovery, lost `uinput` device) is the point of those code paths, so it is
  tested explicitly.

## Lint and format

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

To fix in place:

```bash
.venv/bin/ruff format . && .venv/bin/ruff check --fix .
```

Configuration lives in `pyproject.toml`: line length 110, target `py312`, rule
sets `E`, `F`, `I`, `UP`, `B`, `C4`, `SIM`. Three deliberate ignores — `E501`
(the formatter owns line length), `B904` (`raise ... from` is noise in thin
wrappers), and `SIM105` (`contextlib.suppress` over `try/except/pass`). Tests
additionally ignore `B011` and `SIM117`.

Optional git hooks:

```bash
uv run pre-commit install
```

That runs `ruff --fix`, `ruff-format`, `prettier`, and the standard
whitespace/YAML/TOML checks on every commit.

## Documentation

```bash
uv run --group docs zensical serve         # live reload at http://127.0.0.1:8000
uv run --group docs zensical build --strict
```

`--strict` turns warnings into errors, which is what `docs.yml` runs — a broken
internal link fails the build rather than shipping quietly.

Engineering plans live in `plans/` at the repository root, deliberately outside
`docs_dir`. Zensical does not honour MkDocs' `exclude_docs`, so anything inside
`docs/` gets published; keeping the plans out of that tree is what guarantees
they stay unpublished.

Anchors are the standard slugs: lowercase, punctuation stripped, spaces to
hyphens. `## \`libcublas.so.12\` is not found`becomes`#libcublasso12-is-not-found`.

## Makefile targets

For parity with the VS Code workspace tasks, without VS Code:

```bash
make            # help
make sync       # uv sync --extra cuda --group dev
make test       # full suite
make test-ci    # CI subset
make lint       # ruff check + ruff format --check
make format     # ruff format + ruff check --fix
make docs       # zensical serve
make restart    # restart the user service and print status
make status     # systemctl status + voice-flow status
make logs       # journalctl -f
```

The workspace file also carries `debugpy` launch configurations for
`Daemon (foreground)` and `Toggle once`.

## Testing a change against the live daemon

```bash
systemctl --user restart voice-flow && sleep 3 && ./voice-flow.sh status
```

Expected: `Daemon running: YES (warm in GPU)`.

For anything touching the hotkey listener or the injector, run in the foreground
instead so you can watch the events:

```bash
systemctl --user stop voice-flow
./voice-flow.sh daemon
```

Only one process can own the socket, so always stop the unit first.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`,
`docs:`, `chore:`, `ci:`, `build:`, `test:`, `refactor:`. One logical change per
pull request, and add an entry under `## [Unreleased]` in `CHANGELOG.md` for
anything user-visible.

Before pushing:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
```

## Continuous integration

| Workflow      | Trigger               | What it does                                                                                                                         |
| ------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `ci.yml`      | push and pull request | `uv sync --group dev` (no `cuda` extra — those wheels are 2.2 GB), ruff lint and format check, then `pytest` on Python 3.12 and 3.13 |
| `docs.yml`    | push to `main`        | `zensical build --strict` and deploy to GitHub Pages                                                                                 |
| `release.yml` | tag matching `v*`     | build the wheel and sdist, create a GitHub Release with the matching `CHANGELOG.md` section as the body, attach `dist/*`             |

CI installs without the `cuda` extra deliberately: nothing in the CI subset
imports `ctranslate2`, and the 2.2 GB download would dominate every run.

## Release procedure

Maintainers only. Voice Flow follows a weekly release cycle where feature and fix PRs land on `develop`, and `develop` is merged to `main` over weekends for release.

The version lives in `pyproject.toml` and is mirrored in
`voice_flow/__init__.py` as `__version__`; `bump-my-version` updates both plus
`CHANGELOG.md` in one commit.

1. **Merge `develop` into `main` and write the changelog.** Ensure `## [Unreleased]` in
   `CHANGELOG.md` describes the release under Keep a Changelog headings
   (`Added`, `Changed`, `Fixed`, `Security`).

   ```bash
   git checkout main
   git merge --ff-only develop
   ```

2. **Verify a clean tree.** `bumpversion` is configured with
   `allow_dirty = false` and will refuse otherwise.

   ```bash
   git status --short
   .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
   ```

3. **Bump.** Pick the level per [SemVer](https://semver.org/spec/v2.0.0.html):

   ```bash
   .venv/bin/bump-my-version bump patch --verbose   # or minor / major
   ```

   This rewrites `pyproject.toml`, `voice_flow/__init__.py`, and `CHANGELOG.md`
   (inserting a dated `## [x.y.z]` section below `## [Unreleased]`), commits as
   `chore(release): bump version A -> B`, and creates the annotated tag
   `vB` with the message `release: vB`.

4. **Push the commit and the tag.**

   ```bash
   git push --follow-tags
   ```

5. **Watch the release workflow.**

   ```bash
   gh run watch --exit-status
   gh release view "v$(.venv/bin/python -c 'import voice_flow; print(voice_flow.__version__)')"
   ```

   The release body is the changelog section for that version, with the wheel and
   sdist attached.

Never edit versions by hand — the two files and the tag would drift apart.

## Where to ask

- Bugs and features:
  [issues](https://github.com/khiladisngh/voice-flow/issues)
- Security reports: privately via
  [GitHub Security Advisories](https://github.com/khiladisngh/voice-flow/security/advisories/new),
  never a public issue
- Contribution rules:
  [`CONTRIBUTING.md`](https://github.com/khiladisngh/voice-flow/blob/main/CONTRIBUTING.md)
