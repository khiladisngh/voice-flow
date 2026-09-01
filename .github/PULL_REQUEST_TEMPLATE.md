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

> **CI cannot verify hardware paths.** GitHub Actions runs
> `pytest -m "not uinput and not pipewire"`, which deselects the `uinput` and
> `pipewire` tests. Run the full suite locally on a Wayland machine with
> PipeWire and `input`-group access, and paste the result here.

- [ ] Full local suite run (`uv run pytest`) — paste the summary line:

```text

```

## Checklist

- [ ] Tests added or updated for the changed behaviour
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] Documentation under `docs/` (and the README, if user-facing) updated
