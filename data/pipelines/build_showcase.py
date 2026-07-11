"""Showcase precompute (spec §15): 5 real farms, fully underwritten + presets,
written to apps/web/public/showcase/{id}.json so the demo works with the API asleep.

Selection criteria (§15, deterministic — same mart → same five farms):
  (a) 5 different Bundesländer incl. one southern weak-wind site
  (b) size spread ~10 MW to >50 MW
  (c) vintage spread incl. one ≥2023 and one 2000s-era
  (d) one Senvion-equipped farm (§17.3 story beat)
  (e) clean MaStR records (coords + hub height present)

Memos: generated only when ANTHROPIC_API_KEY is set (run_debate is a live LLM
call); otherwise memo fields are null and the UI shows its degraded state.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from datetime import UTC  # noqa: E402

import duckdb  # noqa: E402

log = logging.getLogger("build_showcase")

PRESET_KEYS = [
    "low_wind_2021",
    "price_crash_2020",
    "negative_hour_surge",
    "rate_shock",
    "capex_overrun",
    "redispatch_tightening",
]


def _candidates(con: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = (
        con.execute(
            """
        SELECT f.*, r.p50_cf, r.method, r.source AS resource_source, r.hub_height_used
        FROM farms f JOIN resource r USING (farm_id)
        WHERE r.p50_cf IS NOT NULL
          AND f.hub_height_m IS NOT NULL
          AND f.commissioning_year IS NOT NULL
          AND f.n_units >= 2
        ORDER BY f.farm_id
        """
        )
        .fetchdf()
        .to_dict("records")
    )
    return rows


def select_showcase(rows: list[dict]) -> list[dict]:
    """Greedy, criteria-first, deterministic (rows arrive sorted by farm_id)."""
    chosen: list[dict] = []
    used_laender: set[str] = set()

    def take(pred, label: str) -> None:
        for r in rows:
            if r["farm_id"] in {c["farm_id"] for c in chosen}:
                continue
            if r["bundesland"] in used_laender:
                continue
            if pred(r):
                chosen.append(r)
                used_laender.add(r["bundesland"])
                log.info(
                    "selected [%s] %s (%s, %.1f MW, %s, %s)",
                    label,
                    r["farm_id"],
                    r["name"],
                    r["mw_total"],
                    r["commissioning_year"],
                    r["bundesland"],
                )
                return
        raise RuntimeError(f"no candidate satisfies showcase criterion: {label}")

    take(
        lambda r: "senvion" in str(r["manufacturer"]).lower() and r["mw_total"] >= 8,
        "senvion",
    )
    take(
        lambda r: r["bundesland"] in ("Bayern", "Baden-Württemberg") and r["mw_total"] >= 8,
        "southern weak-wind",
    )
    take(
        lambda r: r["commissioning_year"] >= 2023 and r["mw_total"] > 50,
        "modern >50MW",
    )
    take(
        lambda r: 2000 <= r["commissioning_year"] <= 2009 and 8 <= r["mw_total"] <= 40,
        "2000s era",
    )
    take(
        lambda r: 10 <= r["mw_total"] <= 30 and r["commissioning_year"] >= 2015,
        "mid-size recent",
    )
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mart", default=str(REPO_ROOT / "data" / "mart" / "rheingold.duckdb"))
    parser.add_argument("--out", default=str(REPO_ROOT / "apps" / "web" / "public" / "showcase"))
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")

    from rheingold_api.routes import UnderwriteRequest, build_underwrite, get_farm

    con = duckdb.connect(args.mart, read_only=True)
    rows = _candidates(con)
    con.close()
    log.info("%d clean candidates", len(rows))
    chosen = select_showcase(rows)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = []
    for r in chosen:
        fid = r["farm_id"]
        farm_detail = get_farm(fid)
        base = build_underwrite(UnderwriteRequest(farm_id=fid))
        presets = {}
        from rheingold_engine import PRESETS

        for key in PRESET_KEYS:
            shocks = PRESETS[key].model_dump()
            presets[key] = build_underwrite(
                UnderwriteRequest(farm_id=fid, shocks=shocks)
            ).model_dump()
        payload = {
            "farm": farm_detail,
            "underwrite": base.model_dump(),
            "presets": presets,
            "memo_markdown": None,  # requires ANTHROPIC_API_KEY at generation time
            "claims": [],
            "rebuttals": [],
            "gate_flags": [f.model_dump() for f in _gate_flags(base)],
            "validation": None,
        }
        path = out_dir / f"{fid}.json"
        path.write_text(json.dumps(payload))
        ids.append(fid)
        log.info("wrote %s (%.0f kB)", path, path.stat().st_size / 1024)

    (out_dir / "index.json").write_text(json.dumps({"showcase_ids": ids}, indent=1))
    log.info("showcase index: %s", ids)
    if not any((Path.cwd() / p).exists() for p in [".env"]):
        log.info("NOTE: memos not generated (no ANTHROPIC_API_KEY) — UI shows degraded memo state")
    return 0


def _gate_flags(result):
    from datetime import datetime

    from rheingold_agents.compliance_gate import run as gate_run

    return gate_run(result, as_of=datetime.now(UTC))


if __name__ == "__main__":
    sys.exit(main())
