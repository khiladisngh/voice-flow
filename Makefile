PY := .venv/bin/python
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
BUMP := .venv/bin/bump-my-version
UV := uv
PRETTIER := npx prettier

.DEFAULT_GOAL := help

.PHONY: help sync setup test test-ci lint format docs docs-build restart status logs toggle \
        bump-patch bump-minor bump-major clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

sync: ## Install runtime, CUDA extra, dev, and docs dependencies
	$(UV) sync --extra cuda --group dev --group docs

setup: sync ## Full dev setup, including the prettier toolchain
	npm install

test: ## Run the full suite (needs input group + PipeWire)
	$(PYTEST)

test-ci: ## Run exactly what CI runs (no uinput, no PipeWire)
	$(PYTEST) -m "not uinput and not pipewire"

lint: ## Check everything CI checks: ruff (Python) + prettier (Markdown/YAML/JSON)
	$(RUFF) check .
	$(RUFF) format --check .
	$(PRETTIER) --check .

format: ## Reformat and autofix in place
	$(RUFF) format .
	$(RUFF) check --fix .
	$(PRETTIER) --write .

docs: ## Serve the docs locally on :8000
	$(UV) run --group docs zensical serve

docs-build: ## Strict docs build, as the docs workflow runs it
	$(UV) run --group docs zensical build --strict

restart: ## Restart the daemon and report status
	systemctl --user restart voice-flow
	@sleep 6
	./voice-flow.sh status

status: ## Show unit state and socket readiness
	-systemctl --user status voice-flow --no-pager
	./voice-flow.sh status

logs: ## Follow the daemon journal
	journalctl --user -u voice-flow -f

toggle: ## Start or stop a dictation session
	./voice-flow.sh toggle

bump-patch: ## Bump patch version, commit, and tag
	$(BUMP) bump patch --verbose

bump-minor: ## Bump minor version, commit, and tag
	$(BUMP) bump minor --verbose

bump-major: ## Bump major version, commit, and tag
	$(BUMP) bump major --verbose

clean: ## Remove build, cache, and docs artefacts
	rm -rf build dist site .pytest_cache .ruff_cache htmlcov .coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
