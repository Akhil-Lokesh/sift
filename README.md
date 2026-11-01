# Sift

A chat router that decides, per message, **which parts of the conversation to send** and **which model should answer**, and only acts when the saving survives prompt-cache costs.

Full design: [docs/SPEC.md](docs/SPEC.md). Verified provider prices and limits: [docs/providers.md](docs/providers.md).

## Status

Step 0 (setup) done. Next: step 1, decision-model smoke test.

## Layout

```
docs/       spec and provider facts (with sources and read dates)
src/sift/   library code
scripts/    one-off runnable scripts (access checks, experiments, log analysis)
tests/      unit tests (no network)
data/       fixed question sets and conversations
results/    raw run outputs and logs, kept for reproducibility
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```sh
uv sync
cp .env.example .env   # then add your keys
uv run pytest
uv run python scripts/check_access.py   # confirms keys and pinned models; no token-billed calls
```

## Pinned models

| Role | Model |
|---|---|
| Decision | `jev-1.14.0` |
| Small | `claude-haiku-5-5` |
| Medium | `claude-sonnet-5-5` |
| Large | `claude-opus-5-5` |
