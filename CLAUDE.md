# CLAUDE.md — rheingold

Read docs/RHEINGOLD_BUILD_SPEC.md before any work. It is authoritative.

## Non-negotiables
- packages/engine is PURE: no network, no LLM, no unseeded randomness. If a task
  needs data, it belongs in data/pipelines; if it needs prose, packages/agents.
- Never fabricate market/registry data. Missing data = raise + stop.
- Golden-farm test (engine/tests/test_golden_farm.py) must pass after every
  engine change. If your change moves its numbers, your change is wrong or the
  spec changed — say which, explicitly.
- All numbers rendered in UI use lib/format.ts (de-DE, tabular mono).
- Colors/fonts only via CSS variables from §3.1. No hex literals in components.
- Every new data source gets a row in docs/DATA_SOURCES.md (license included).
- VERIFY: tags in the spec mean check-before-hardcode. Log findings in the PR/commit.

## Workflow
- Work phase-by-phase (§14). State the phase at the start of each session.
- Plan (files, order, tests) before code. TDD on engine. Conventional commits.
- Run: make engine-test before any commit touching packages/engine.
- Do not add scope from §0.2 even if asked casually mid-session; flag it instead.

## Commands
make data | make engine-test | make dev | make backtest | make showcase | make deploy
