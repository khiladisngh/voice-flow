# Summary

<!-- What does this change do, and why? One or two sentences. -->

## Related issue

<!-- e.g. Closes #12. Write "None" for trivial changes. -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (existing config, CLI, or API behaviour changes)
- [ ] Documentation only
- [ ] Build, CI, or tooling

## Verification

List the commands you ran and their results.

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

> **Keep the suite hermetic.** No test may open `/dev/uinput`, synthesize a
> keystroke, write the clipboard, or spawn `pw-record` — CI runs the full suite
> on a runner with none of that hardware. If you touched `tests/`, confirm the
> clipboard canary in `CONTRIBUTING.md` still survives the run.

- [ ] Full suite run (`uv run pytest`) — paste the summary line:

```text

```

## Checklist

- [ ] Tests added or updated for the changed behaviour
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] Documentation under `docs/` (and the README, if user-facing) updated
