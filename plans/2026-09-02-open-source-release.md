# Voice Flow Open-Source Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the hardened `voice-flow` working directory into a public, documented, CI-verified open-source project on `github.com/khiladisngh/voice-flow`, released as `v0.1.0`.

**Architecture:** A flat-layout `uv`-built Python package. Heavy CUDA runtime wheels move to an optional `cuda` extra so GitHub runners can install the project; hardware-bound tests self-skip via capability probes so the same suite is green in CI and locally. GitHub Actions covers lint/test, MkDocs deployment, and tag-triggered releases. A VS Code multi-root workspace exposes every operation as a task so nothing requires memorised shell invocations.

**Tech Stack:** Python 3.12/3.13, uv 0.12.5, pytest 9, ruff, bump-my-version, MkDocs Material, GitHub Actions, gh CLI 2.98.0.

**Spec:** This document is self-contained; it derives from the user's stated requirements (README with badges, open-source LICENSE, CONTRIBUTING, bumpversion + tagging, CHANGELOG, GitHub workflows, documentation, `.code-workspace` with tasks, publish to the `khiladisngh` account) and from the completed hardening plan at `docs/superpowers/plans/2026-09-02-voice-flow-hardening.md`.

## Global Constraints

- GitHub owner: `khiladisngh`. Repository name: `voice-flow`. Remote protocol: SSH (`gh` is configured for SSH).
- Default branch MUST be `main` (currently `master` — rename before publishing).
- License: MIT, copyright holder `Gishant Singh`, year `2026`.
- Version source of truth: `0.1.0` in `pyproject.toml`, mirrored in `voice_flow/__init__.py` as `__version__`.
- Release tags MUST be `v{version}` (e.g. `v0.1.0`); changelog format MUST be Keep a Changelog 1.1.0 with Semantic Versioning 2.0.0.
- `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` total 2.2 GB installed and MUST NOT be in `[project.dependencies]`; they belong to an optional extra named `cuda`. Documented install command is `uv sync --extra cuda`.
- CI MUST NOT require `/dev/uinput`, PipeWire, an NVIDIA GPU, or a Wayland session. Tests needing those carry the `uinput` or `pipewire` marker and self-skip via `tests/conftest.py` capability probes.
- No secrets, tokens, absolute home paths, or machine-specific hostnames in any committed file. Systemd units use `%h`, not `~`.
- The running `voice-flow.service` MUST still be active and answering `voice-flow.sh status` at the end.
- Every task ends with a commit. Conventional Commits prefixes (`feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `build:`).

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, `cuda` extra, ruff/pytest/coverage/bumpversion config |
| `voice_flow/__init__.py` | Package docstring + `__version__` (bump target) |
| `tests/conftest.py` | sys.path bootstrap + `uinput`/`pipewire` capability skip hook |
| `LICENSE` | MIT text |
| `README.md` | Badges, pitch, benchmark, install, usage, config, architecture diagram |
| `CHANGELOG.md` | Keep a Changelog; `## [Unreleased]` anchor consumed by bump-my-version |
| `CONTRIBUTING.md` | Dev setup, test/lint commands, hardware-marker rules, commit + release flow |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1 |
| `SECURITY.md` | Supported versions, private reporting, local-privilege threat model |
| `voice-flow.code-workspace` | Multi-root workspace: settings, extensions, tasks, launch configs |
| `Makefile` | CLI parity with workspace tasks for non-VS-Code users |
| `.pre-commit-config.yaml` | ruff lint + format hooks |
| `.github/workflows/ci.yml` | Lint + test matrix (3.12, 3.13) |
| `.github/workflows/docs.yml` | MkDocs build + GitHub Pages deploy |
| `.github/workflows/release.yml` | Tag-triggered build + GitHub Release with changelog body |
| `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml` | Structured intake |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR checklist |
| `.github/dependabot.yml` | Weekly pip + actions updates |
| `mkdocs.yml` | Material theme, nav, `exclude_docs` for `superpowers/` |
| `docs/{index,installation,usage,configuration,architecture,troubleshooting,development}.md` | Documentation site pages |
| `docs/superpowers/plans/*.md` | Retained planning history, excluded from the docs site |

---

### Task 1: Packaging, CUDA Extra, and Test Capability Gating

Partially applied already (uncommitted): `pyproject.toml` metadata/tooling, `tests/conftest.py` probes, `uinput`/`pipewire` markers on `tests/test_injector.py` and `tests/test_recorder.py`. This task completes and verifies it.

**Files:**
- Modify: `pyproject.toml`
- Modify: `voice_flow/__init__.py`
- Verify: `tests/conftest.py`, `tests/test_injector.py`, `tests/test_recorder.py`

**Interfaces:**
- Produces: `voice_flow.__version__ == "0.1.0"`; extra `cuda`; pytest markers `uinput`, `pipewire`; ruff config at line-length 110.
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Move CUDA wheels out of runtime dependencies**

In `pyproject.toml`, `[project].dependencies` MUST be exactly:

```toml
dependencies = [
    "evdev>=2.0.0",
    "faster-whisper>=1.2.1",
    "requests>=2.34.2",
]

[project.optional-dependencies]
cuda = [
    "nvidia-cublas-cu12>=12.9.2.10",
    "nvidia-cudnn-cu12>=9.25.1.1",
]
```

- [ ] **Step 2: Add the version attribute to the package**

Replace `voice_flow/__init__.py` with:

```python
"""Voice Flow: GPU-accelerated, fully offline voice dictation for Linux/Wayland."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Re-sync the environment with the extra and confirm CUDA still resolves**

```bash
uv sync --extra cuda --group dev
.venv/bin/python -c "import voice_flow; print(voice_flow.__version__)"
.venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```
Expected: `0.1.0`, then `1`.

- [ ] **Step 4: Confirm the suite passes with markers and strict mode**

```bash
.venv/bin/pytest
```
Expected: `51 passed` (no marker warnings — `--strict-markers` is on).

- [ ] **Step 5: Confirm the CI subset passes without hardware**

```bash
.venv/bin/pytest -m "not uinput and not pipewire"
```
Expected: `40 passed, 11 deselected`.

- [ ] **Step 6: Lint clean**

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```
Expected: no errors. Fix any reported violation, then re-run.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml voice_flow/__init__.py tests/
git commit -m "build: split cuda runtime into optional extra and gate hardware tests"
```

---

### Task 2: Legal and Community Health Files

**Files:**
- Create: `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`

**Interfaces:**
- Produces: `CHANGELOG.md` containing the literal line `## [Unreleased]` (bump-my-version rewrites this anchor); `LICENSE` recognised by GitHub as MIT.
- Consumes: version `0.1.0` from Task 1.

- [ ] **Step 1: Write `LICENSE`**

Standard MIT text, first two lines:

```
MIT License

Copyright (c) 2026 Gishant Singh
```

Followed by the unmodified MIT permission, condition, and warranty-disclaimer paragraphs.

- [ ] **Step 2: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-02

### Added

- Offline dictation daemon: `faster-whisper` `large-v3-turbo` on CUDA (`int8_float16`) with a warm model held in VRAM.
- Local LLM post-processing via Ollama (`qwen2.5:1.5b`) that strips fillers and restores punctuation.
- Kernel-level global hotkey (`Right Ctrl + Right Alt`) over `evdev`, supporting both push-to-talk and tap-to-toggle.
- Wayland text injection through `wl-copy` plus a persistent `uinput` virtual keyboard, with clipboard restore.
- Unix-socket IPC with newline-delimited JSON framing, and a `systemd` user service.
- Documentation site, VS Code workspace tasks, and a 51-test suite.

### Security

- Runtime artefacts (audio, PID, socket) live in `$XDG_RUNTIME_DIR/voice-flow` at mode `0700` instead of world-writable `/dev/shm`.
- Dictated speech is wrapped in `<spoken_text>` delimiters before reaching the LLM to contain prompt injection.

[Unreleased]: https://github.com/khiladisngh/voice-flow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/khiladisngh/voice-flow/releases/tag/v0.1.0
```

- [ ] **Step 3: Write `CONTRIBUTING.md`**

MUST contain these sections with working commands:
1. **Prerequisites** — Linux + Wayland, Python ≥3.12, `uv`, PipeWire (`pw-record`), `wl-clipboard`, membership of the `input` group (`sudo usermod -aG input $USER`), optional NVIDIA GPU + Ollama.
2. **Setup** — `git clone`, `uv sync --extra cuda --group dev`, `.venv/bin/pytest`.
3. **Tests** — full run `.venv/bin/pytest`; CI-equivalent run `.venv/bin/pytest -m "not uinput and not pipewire"`; explanation that `uinput` and `pipewire` markers self-skip when the capability is absent, and that any new test touching real devices MUST carry the matching marker.
4. **Lint** — `.venv/bin/ruff check .`, `.venv/bin/ruff format .`, optional `pre-commit install`.
5. **Commits** — Conventional Commits, one logical change per PR, changelog entry under `## [Unreleased]`.
6. **Release** — maintainers only: `bump-my-version bump patch|minor|major`, then `git push --follow-tags`, which triggers `release.yml`.
7. **Architecture pointer** — link to `docs/architecture.md`.

- [ ] **Step 4: Write `CODE_OF_CONDUCT.md`**

Contributor Covenant 2.1, verbatim, with the reporting contact set to the GitHub profile `https://github.com/khiladisngh` (do not invent an email address).

- [ ] **Step 5: Write `SECURITY.md`**

MUST state: supported version is the latest `0.1.x`; report privately via GitHub Security Advisories (`https://github.com/khiladisngh/voice-flow/security/advisories/new`) rather than public issues; expected first response within 7 days. Threat-model section MUST note that the daemon reads all keyboard input via `/dev/input`, writes synthetic keystrokes via `/dev/uinput`, keeps recorded audio in `$XDG_RUNTIME_DIR` at mode `0700`, and sends transcripts only to a user-configured local Ollama endpoint — no network egress by default.

- [ ] **Step 6: Commit**

```bash
git add LICENSE CHANGELOG.md CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md
git commit -m "docs: add license, changelog, and community health files"
```

---

### Task 3: README with Badges

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: install command from Task 1 (`uv sync --extra cuda`), workflow filenames from Task 5 (`ci.yml`, `docs.yml`), docs URL `https://khiladisngh.github.io/voice-flow/`.

- [ ] **Step 1: Write the badge block**

Directly under the `# Voice Flow` heading and one-line tagline:

```markdown
[![CI](https://github.com/khiladisngh/voice-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/khiladisngh/voice-flow/actions/workflows/ci.yml)
[![Docs](https://github.com/khiladisngh/voice-flow/actions/workflows/docs.yml/badge.svg)](https://khiladisngh.github.io/voice-flow/)
[![Release](https://img.shields.io/github/v/release/khiladisngh/voice-flow?sort=semver)](https://github.com/khiladisngh/voice-flow/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Wayland-informational.svg)](https://wayland.freedesktop.org/)
[![CUDA](https://img.shields.io/badge/NVIDIA-CUDA%20accelerated-76B900.svg?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![Offline](https://img.shields.io/badge/privacy-100%25%20offline-success.svg)](#privacy)
```

- [ ] **Step 2: Write the body sections in this order**

1. **Why** — one paragraph: a ~2 GB Electron dictation app replaced by a ~85 MB resident daemon at ~200 ms latency, fully offline.
2. **Benchmark table** — columns Component / Engine / Latency / Footprint, with the measured rows: STT `whisper-large-v3-turbo` `int8_float16` ~120 ms / ~1.1 GB VRAM; cleanup `qwen2.5:1.5b` 66 ms / ~1.2 GB VRAM; capture PipeWire <5 ms / 0 MB; injection `wl-copy` + `uinput` ~15 ms / 0 MB; total ~200 ms / ~85 MB RAM. State plainly that figures are measured on an RTX 3070.
3. **Requirements** — Linux + Wayland (developed on Fedora + KDE Plasma 6), Python ≥3.12, `uv`, PipeWire, `wl-clipboard`, `input` group membership, NVIDIA GPU (optional; CPU works but slower), Ollama (optional; disable cleanup otherwise).
4. **Install** — clone, `uv sync --extra cuda`, `ollama pull qwen2.5:1.5b`, `cp voice-flow.service ~/.config/systemd/user/`, `systemctl --user enable --now voice-flow`. Note the first run downloads the Whisper model (~1.6 GB) into the Hugging Face cache.
5. **Usage** — `Right Ctrl + Right Alt`: hold to push-to-talk, tap to toggle; CLI table for `toggle`, `status`, `daemon`, `record-start`, `record-stop`.
6. **Configuration** — the full `config.json` fenced as JSON with a table describing `hotkey.combo`, `hotkey.hold_threshold_sec`, `stt.model_size`, `stt.compute_type`, `stt.language`, `cleaner.enabled`, `cleaner.model`, `ui.restore_clipboard`.
7. **Architecture** — the mermaid diagram below.
8. **Privacy** — anchor `#privacy`: audio never leaves the machine; transcripts go only to the local Ollama endpoint; artefacts are mode `0700` in `$XDG_RUNTIME_DIR`.
9. **Development** — `uv sync --extra cuda --group dev`, `.venv/bin/pytest`, pointer to `CONTRIBUTING.md`.
10. **Acknowledgements** — faster-whisper, CTranslate2, OpenAI Whisper, Ollama/Qwen, python-evdev, wl-clipboard.
11. **License** — MIT, link to `LICENSE`.

Architecture diagram to embed verbatim:

````markdown
```mermaid
graph LR
    A[Right Ctrl + Right Alt] -->|evdev| B[Hotkey Listener]
    B --> C[PipeWire pw-record]
    C -->|WAV in XDG_RUNTIME_DIR| D[faster-whisper CUDA]
    D -->|raw text| E[Ollama qwen2.5:1.5b]
    E -->|clean text| F[wl-copy + uinput Ctrl+V]
    F --> G[Active Wayland Window]
```
````

- [ ] **Step 3: Verify no absolute home paths leaked**

```bash
grep -n "~" README.md || echo "clean"
```
Expected: `clean`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: rewrite readme with badges, benchmarks, and architecture"
```

---

### Task 4: VS Code Workspace, Tasks, and Makefile

**Files:**
- Create: `voice-flow.code-workspace`, `Makefile`, `.pre-commit-config.yaml`
- Modify: `.gitignore`

**Interfaces:**
- Produces: workspace tasks named `sync`, `test`, `test: ci subset`, `lint`, `format`, `daemon: restart`, `daemon: status`, `daemon: logs`, `dictate: toggle`, `docs: serve`, `release: bump patch`.
- Consumes: `uv sync --extra cuda --group dev` from Task 1, `mkdocs serve` from Task 6.

- [ ] **Step 1: Write `voice-flow.code-workspace`**

```json
{
  "folders": [{ "name": "voice-flow", "path": "." }],
  "settings": {
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": false,
    "python.testing.pytestArgs": ["tests"],
    "python.analysis.extraPaths": ["${workspaceFolder}"],
    "files.exclude": { "**/__pycache__": true, "**/*.egg-info": true },
    "files.trimTrailingWhitespace": true,
    "files.insertFinalNewline": true,
    "editor.rulers": [110],
    "[python]": {
      "editor.defaultFormatter": "charliermarsh.ruff",
      "editor.formatOnSave": true,
      "editor.codeActionsOnSave": { "source.organizeImports.ruff": "explicit" }
    },
    "yaml.schemas": {
      "https://json.schemastore.org/github-workflow.json": ".github/workflows/*.yml"
    }
  },
  "extensions": {
    "recommendations": [
      "ms-python.python",
      "charliermarsh.ruff",
      "redhat.vscode-yaml",
      "tamasfe.even-better-toml",
      "bierner.markdown-mermaid"
    ]
  },
  "tasks": {
    "version": "2.0.0",
    "options": { "cwd": "${workspaceFolder}" },
    "presentation": { "panel": "dedicated", "clear": true },
    "tasks": [
      {
        "label": "sync",
        "type": "shell",
        "command": "uv sync --extra cuda --group dev",
        "problemMatcher": []
      },
      {
        "label": "test",
        "type": "shell",
        "command": "${workspaceFolder}/.venv/bin/pytest",
        "group": { "kind": "test", "isDefault": true },
        "problemMatcher": []
      },
      {
        "label": "test: ci subset",
        "type": "shell",
        "command": "${workspaceFolder}/.venv/bin/pytest -m 'not uinput and not pipewire'",
        "problemMatcher": []
      },
      {
        "label": "lint",
        "type": "shell",
        "command": "${workspaceFolder}/.venv/bin/ruff check . && ${workspaceFolder}/.venv/bin/ruff format --check .",
        "group": { "kind": "build", "isDefault": true },
        "problemMatcher": []
      },
      {
        "label": "format",
        "type": "shell",
        "command": "${workspaceFolder}/.venv/bin/ruff format . && ${workspaceFolder}/.venv/bin/ruff check --fix .",
        "problemMatcher": []
      },
      {
        "label": "daemon: restart",
        "type": "shell",
        "command": "systemctl --user restart voice-flow && sleep 3 && ./voice-flow.sh status",
        "problemMatcher": []
      },
      {
        "label": "daemon: status",
        "type": "shell",
        "command": "systemctl --user status voice-flow --no-pager; ./voice-flow.sh status",
        "problemMatcher": []
      },
      {
        "label": "daemon: logs",
        "type": "shell",
        "command": "journalctl --user -u voice-flow -f",
        "isBackground": true,
        "problemMatcher": []
      },
      {
        "label": "dictate: toggle",
        "type": "shell",
        "command": "./voice-flow.sh toggle",
        "problemMatcher": []
      },
      {
        "label": "docs: serve",
        "type": "shell",
        "command": "uv run --group docs mkdocs serve",
        "isBackground": true,
        "problemMatcher": []
      },
      {
        "label": "release: bump patch",
        "type": "shell",
        "command": "${workspaceFolder}/.venv/bin/bump-my-version bump patch --verbose",
        "problemMatcher": []
      }
    ]
  },
  "launch": {
    "version": "0.2.0",
    "configurations": [
      {
        "name": "Daemon (foreground)",
        "type": "debugpy",
        "request": "launch",
        "module": "voice_flow.main",
        "args": ["daemon"],
        "console": "integratedTerminal",
        "justMyCode": false
      },
      {
        "name": "Toggle once",
        "type": "debugpy",
        "request": "launch",
        "module": "voice_flow.main",
        "args": ["toggle"],
        "console": "integratedTerminal"
      }
    ]
  }
}
```

- [ ] **Step 2: Write `Makefile`** (tab-indented recipes)

Targets `help` (default), `sync`, `test`, `test-ci`, `lint`, `format`, `docs`, `restart`, `status`, `logs`, `bump-patch`, `bump-minor`, `bump-major`, mapping one-to-one onto the workspace task commands above. Declare `.PHONY` for all of them.

- [ ] **Step 3: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict
```

- [ ] **Step 4: Extend `.gitignore`**

Append: `.ruff_cache/`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `site/`, `*.wav`.

- [ ] **Step 5: Verify the workspace JSON parses and a task command works**

```bash
.venv/bin/python -c "import json;json.load(open('voice-flow.code-workspace'));print('workspace json ok')"
make test-ci
```
Expected: `workspace json ok`, then `40 passed, 11 deselected`.

- [ ] **Step 6: Commit**

```bash
git add voice-flow.code-workspace Makefile .pre-commit-config.yaml .gitignore
git commit -m "chore: add vscode workspace tasks, makefile, and pre-commit hooks"
```

---

### Task 5: GitHub Workflows and Repository Templates

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/docs.yml`, `.github/workflows/release.yml`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/ISSUE_TEMPLATE/feature_request.yml`, `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`, `.github/dependabot.yml`

**Interfaces:**
- Consumes: `uv sync --group dev` (no `cuda` extra in CI), marker expression `not uinput and not pipewire`, `mkdocs.yml` from Task 6.
- Produces: workflow badge URLs used by Task 3.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --group dev
      - run: uv run ruff check --output-format=github .
      - run: uv run ruff format --check .

  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
          python-version: ${{ matrix.python-version }}
      - run: uv sync --group dev
      - name: Run tests (hardware-dependent tests are skipped)
        run: uv run pytest -m "not uinput and not pipewire" --cov=voice_flow --cov-report=term-missing

  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv build
      - uses: actions/upload-artifact@v5
        with:
          name: dist
          path: dist/
```

- [ ] **Step 2: Write `.github/workflows/docs.yml`**

```yaml
name: Docs

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv run --group docs mkdocs build --strict
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v4
        with:
          path: site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 3: Write `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: uv sync --group dev
      - run: uv run pytest -m "not uinput and not pipewire"
      - run: uv build
      - name: Extract changelog section for this tag
        id: notes
        run: |
          VERSION="${GITHUB_REF_NAME#v}"
          awk -v ver="$VERSION" '
            $0 ~ "^## \\[" ver "\\]" { found=1; next }
            found && /^## \[/ { exit }
            found { print }
          ' CHANGELOG.md > release-notes.md
          if [ ! -s release-notes.md ]; then
            echo "No changelog section found for $VERSION" >&2
            exit 1
          fi
      - uses: softprops/action-gh-release@v2
        with:
          body_path: release-notes.md
          files: dist/*
          generate_release_notes: false
```

- [ ] **Step 4: Write the issue templates**

`bug_report.yml` — form with required fields: what happened, reproduction steps, expected behaviour; dropdown for desktop environment (KDE Plasma / GNOME / Sway / Hyprland / other); inputs for distro, GPU, `voice-flow` version; textarea for `journalctl --user -u voice-flow -n 50` output; checkboxes confirming the reporter is in the `input` group and that `pw-record`/`wl-copy` exist.

`feature_request.yml` — problem statement, proposed solution, alternatives considered, willingness to submit a PR.

`config.yml`:

```yaml
blank_issues_enabled: false
contact_links:
  - name: Security vulnerability
    url: https://github.com/khiladisngh/voice-flow/security/advisories/new
    about: Report vulnerabilities privately, not as public issues.
```

- [ ] **Step 5: Write `.github/PULL_REQUEST_TEMPLATE.md`**

Sections: Summary; Related issue; Type of change (checkbox list); Verification (commands run, with an explicit reminder that hardware-marked tests must be run locally because CI skips them); Checklist (tests added/updated, `ruff check` clean, `CHANGELOG.md` updated under `## [Unreleased]`, docs updated).

- [ ] **Step 6: Write `.github/dependabot.yml`**

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    commit-message:
      prefix: "build"
  - package-ecosystem: github-actions
    directory: "/"
    schedule:
      interval: weekly
    commit-message:
      prefix: "ci"
```

- [ ] **Step 7: Validate every YAML file parses**

```bash
.venv/bin/python - <<'PY'
import pathlib, sys
try:
    import yaml
except ImportError:
    sys.exit("PyYAML missing: run 'uv pip install pyyaml' first")
for p in sorted(pathlib.Path(".github").rglob("*.yml")):
    yaml.safe_load(p.read_text())
    print("ok", p)
PY
```
Expected: one `ok` line per file, no traceback.

- [ ] **Step 8: Commit**

```bash
git add .github
git commit -m "ci: add lint/test/docs/release workflows and issue templates"
```

---

### Task 6: MkDocs Documentation Site

**Files:**
- Create: `mkdocs.yml`
- Create: `docs/index.md`, `docs/installation.md`, `docs/usage.md`, `docs/configuration.md`, `docs/architecture.md`, `docs/troubleshooting.md`, `docs/development.md`

**Interfaces:**
- Consumes: install/usage/config content from Task 3 (do not contradict the README).
- Produces: a site that builds under `mkdocs build --strict`, which Task 5's `docs.yml` requires.

- [ ] **Step 1: Write `mkdocs.yml`**

```yaml
site_name: Voice Flow
site_description: GPU-accelerated, fully offline voice dictation for Linux/Wayland
site_url: https://khiladisngh.github.io/voice-flow/
repo_url: https://github.com/khiladisngh/voice-flow
repo_name: khiladisngh/voice-flow
edit_uri: edit/main/docs/

theme:
  name: material
  icon:
    repo: fontawesome/brands/github
  palette:
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: green
      accent: light green
      toggle:
        icon: material/weather-sunny
        name: Switch to light mode
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: green
      accent: green
      toggle:
        icon: material/weather-night
        name: Switch to dark mode
  features:
    - navigation.instant
    - navigation.tracking
    - navigation.sections
    - navigation.top
    - content.code.copy
    - search.suggest

exclude_docs: |
  superpowers/

nav:
  - Home: index.md
  - Installation: installation.md
  - Usage: usage.md
  - Configuration: configuration.md
  - Architecture: architecture.md
  - Troubleshooting: troubleshooting.md
  - Development: development.md

markdown_extensions:
  - admonition
  - attr_list
  - tables
  - toc:
      permalink: true
  - pymdownx.details
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - pymdownx.snippets
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
```

- [ ] **Step 2: Write the page contents**

- `index.md` — value proposition, benchmark table (same numbers as the README), feature list, next-step links.
- `installation.md` — system packages per distro (`dnf install pipewire-utils wl-clipboard` / `apt install pipewire-bin wl-clipboard`), `input` group setup with the warning that a re-login is required, `uv sync --extra cuda`, Ollama model pull, systemd unit install, plus a CPU-only fallback (`stt.device: "cpu"`, `stt.compute_type: "int8"`).
- `usage.md` — hotkey behaviour (hold vs tap), every CLI subcommand, binding an alternative shortcut through KDE System Settings, and how to disable the built-in listener via `hotkey.enabled: false`.
- `configuration.md` — every `config.json` key: type, default, effect. Include the `evdev` key-name reference (`KEY_RIGHTCTRL`, `KEY_RIGHTALT`, `KEY_F8`, …) and Whisper model/compute-type trade-offs with VRAM figures.
- `architecture.md` — the mermaid pipeline diagram, one subsection per module (`paths`, `recorder`, `transcriber`, `cleaner`, `injector`, `hotkey`, `daemon`, `main`), the IPC framing contract, and the security decisions (mode `0700` runtime dir, persistent `uinput`, prompt-injection delimiters).
- `troubleshooting.md` — symptom/cause/fix table covering: hotkey does nothing (not in `input` group; check `journalctl` for the `[Hotkey] Listening to keyboard` lines), paste inserts stale clipboard content (raise the restore delay), `libcublas.so.12 not found` (install the `cuda` extra), no audio captured (`pw-record` missing or wrong default source), daemon fails to start (`systemctl --user status`), Ollama unreachable (cleanup silently falls back to raw text).
- `development.md` — repo layout, the hardware-marker testing contract, lint commands, release procedure.

- [ ] **Step 3: Verify a strict build succeeds**

```bash
uv run --group docs mkdocs build --strict
```
Expected: `INFO - Documentation built in ...` with no warnings. Strict mode fails on broken internal links — fix any it reports.

- [ ] **Step 4: Commit**

```bash
git add mkdocs.yml docs/
git commit -m "docs: add mkdocs material documentation site"
```

---

### Task 7: Publish to GitHub and Cut the v0.1.0 Release

**Files:**
- Modify: none (git and GitHub operations only)

**Interfaces:**
- Consumes: every artefact from Tasks 1-6.

- [ ] **Step 1: Rename the default branch**

```bash
git branch -M master main
git branch --show-current
```
Expected: `main`.

- [ ] **Step 2: Confirm the tree is clean and no secrets are staged**

```bash
git status --short
grep -rn "~" --include="*.md" --include="*.yml" --include="*.toml" --include="*.json" . \
  --exclude-dir=.venv --exclude-dir=.git --exclude-dir=docs/superpowers || echo "no absolute home paths"
```
Expected: empty status; `no absolute home paths`. `voice-flow.service` must use `%h`.

- [ ] **Step 3: Create the public repository and push**

```bash
gh repo create khiladisngh/voice-flow \
  --public \
  --source=. \
  --remote=origin \
  --description "GPU-accelerated, fully offline voice dictation for Linux/Wayland — Whisper on CUDA with local LLM cleanup, ~85 MB RAM" \
  --homepage "https://khiladisngh.github.io/voice-flow/" \
  --push
```
Expected: repository created, `main` pushed. Verify with `gh repo view khiladisngh/voice-flow --json name,visibility,defaultBranchRef`.

- [ ] **Step 4: Set discovery topics**

```bash
gh repo edit khiladisngh/voice-flow --add-topic speech-to-text,dictation,whisper,wayland,linux,cuda,ollama,offline,privacy,python
```

- [ ] **Step 5: Enable GitHub Pages for the docs workflow**

```bash
gh api -X POST repos/khiladisngh/voice-flow/pages -f build_type=workflow || \
gh api -X PUT repos/khiladisngh/voice-flow/pages -f build_type=workflow
```
Expected: HTTP 201 or 204. If the API rejects it, record that Pages must be switched to "GitHub Actions" manually in repository settings, and continue.

- [ ] **Step 6: Wait for CI to pass on `main`**

```bash
gh run list --limit 5
gh run watch --exit-status
```
Expected: `CI` and `Docs` conclude `success`. If a run fails, read `gh run view --log-failed`, fix the cause, commit, push, and re-check before tagging.

- [ ] **Step 7: Tag `v0.1.0` and trigger the release**

The changelog already contains a `## [0.1.0]` section from Task 2, so create the tag directly rather than bumping:

```bash
git tag -a v0.1.0 -m "release: v0.1.0"
git push origin v0.1.0
gh run watch --exit-status
```
Expected: the `Release` workflow succeeds and publishes a release whose body is the `0.1.0` changelog section, with `dist/*` attached.

- [ ] **Step 8: Verify the published release**

```bash
gh release view v0.1.0 --json tagName,assets,body --jq '{tag:.tagName, assets:[.assets[].name], body:.body}'
```
Expected: tag `v0.1.0`, one `.whl` and one `.tar.gz` asset, non-empty body.

- [ ] **Step 9: Confirm the local daemon is unaffected**

```bash
systemctl --user restart voice-flow && sleep 3 && ./voice-flow.sh status
```
Expected: `Daemon running: YES (warm in GPU)`.

---

## Self-Review

**1. Spec coverage**

| Requirement | Task |
|---|---|
| Commit everything | Tasks 1-6 each end in a commit; Task 7 Step 2 asserts a clean tree |
| New repo, published | Task 7 Steps 3-4 |
| README with badges | Task 3 |
| Open-source LICENSE | Task 2 Step 1 |
| CONTRIBUTING | Task 2 Step 3 |
| Tagging + bumpversion | Task 1 (`[tool.bumpversion]` already in `pyproject.toml`), Task 4 Step 1 (`release: bump patch` task), Task 7 Step 7 (tag) |
| CHANGELOG | Task 2 Step 2 |
| GitHub workflows | Task 5 Steps 1-3 |
| Documentation | Task 6 |
| `.code-workspace` with tasks | Task 4 Step 1 |
| First release | Task 7 Steps 7-8 |

**2. Placeholder scan** — no `TBD`/`TODO`/"similar to Task N". All config files are given verbatim; prose files are specified section-by-section with the exact commands and figures they must contain.

**3. Type consistency** — `uv sync --extra cuda --group dev` (local) vs `uv sync --group dev` (CI) used consistently; marker expression `not uinput and not pipewire` identical in `ci.yml`, `release.yml`, the Makefile, and the workspace task; workflow filenames `ci.yml`/`docs.yml` match the Task 3 badge URLs; `## [Unreleased]` anchor matches the `[[tool.bumpversion.files]]` search string; version `0.1.0` consistent across `pyproject.toml`, `voice_flow/__init__.py`, `CHANGELOG.md`, and the `v0.1.0` tag.

**Known risk:** Task 5 Step 7 needs PyYAML, which is already present transitively via `faster-whisper`. If it ever isn't, the snippet exits with an actionable message rather than a traceback.
