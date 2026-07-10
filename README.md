# RHEINGOLD

**Underwriting the Energiewende.** Pick any real wind farm in Germany → get a
full, cited investment-committee memo — valuation, debt capacity, stress tests —
in about two minutes.

<!-- HERO GIF: the 20s clip (§1) goes here -->

## Why this exists

Every input is live public German data: the MaStR registry, SMARD prices, BNetzA
auctions, Netztransparenz market values. The finance core is deterministic and
auditable; the agent layer only narrates evidence it can cite. And the
availability and O&M assumptions come from someone who spent two years building
manufacturing data systems across 10+ wind plants at Suzlon — watching real
turbines fail and recover.

## Architecture

```mermaid
flowchart LR
  A[MaStR] --> P[pipelines]
  B[SMARD] --> P
  C[Netztransparenz] --> P
  D[BNetzA auctions CSV] --> P
  E[Wind resource: ninja / GWA] --> P
  P --> M[(DuckDB mart)]
  M --> API[FastAPI]
  API --> ENG[Deterministic engine]
  ENG --> EV[(EvidenceStore)]
  EV --> GATE[Compliance gate - code]
  EV --> CR[3 critics - Claude]
  CR --> N[Narrator - Claude]
  GATE --> N
  N --> V{Citation validator}
  V -->|pass| UI[Next.js: map / dossier / memo]
  V -->|fail| CR
  UI --> H[Human veto]
```

The deterministic engine (`packages/engine`) is pure Python — no network, no
LLM, no unseeded randomness. Agents read a frozen EvidenceStore and argue about
it; a citation-integrity validator they cannot talk their way past rejects any
memo whose numbers don't trace to evidence.

## Screenshots

<!-- map · dossier · memo · backtest -->

## Data sources & licenses

See [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md). Highlights: MaStR
(DL-DE/BY-2.0), SMARD (CC BY 4.0), Netztransparenz (attribution),
renewables.ninja (**CC BY-NC 4.0 — this project is non-commercial**).

## Results

<!-- backtest: "Median model bid tracks the observed award-price trajectory
2017–2025 with MAE ≈ X ct/kWh" — filled from `make backtest`, never promised
before measuring. -->

## Limitations

The honest section. See [docs/MODEL_CARD.md](docs/MODEL_CARD.md): annual (not
monthly) debt model, two-pass tax (no Zinsschranke, no loss carryforward),
single-int §51 modeling, merchant tail without a forward curve, Path B resource
error, and every backtest caveat (winner's curse, undersubscribed rounds,
binding price caps, site-selection bias).

## Run locally

```bash
cp .env.example .env       # add ANTHROPIC_API_KEY for memos (optional)
make data                  # MaStR + SMARD + Marktwerte + fleet build (~30 min first run)
make dev                   # web :3000 + api :8000
make engine-test           # the golden farm must always pass
```

## Author

Siddharth Jain — manufacturing → capital.
*Das neue Rheingold ist Wind.*
