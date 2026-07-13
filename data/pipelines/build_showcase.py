"""Showcase precompute (spec §15): 5 real farms, fully underwritten + presets,
written to apps/web/public/showcase/{id}.json so the demo works with the API asleep.

Selection criteria (§15, deterministic — same mart → same five farms):
  (a) 5 different Bundesländer incl. one southern weak-wind site
  (b) size spread ~10 MW to >50 MW
  (c) vintage spread incl. one ≥2023 and one 2000s-era
  (d) one Senvion-equipped farm (§17.3 story beat)
  (e) clean MaStR records (coords + hub height present)

Memos: generated best-effort when a provider key is set (ANTHROPIC_API_KEY, or
GROQ_API_KEY for the deployment fallback). Generation is per-farm and never
aborts the batch — a farm whose memo fails (provider budget, validation) ships
with memo_markdown=null and the reason recorded, and the UI shows its degraded
state. Pass --no-memos to skip generation entirely.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))


def _load_env() -> None:
    """Load .env (ANTHROPIC_API_KEY / GROQ_API_KEY) without overriding real env."""
    import os

    env = REPO_ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

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
    parser.add_argument(
        "--no-memos",
        dest="memos",
        action="store_false",
        help="skip memo generation entirely",
    )
    parser.add_argument(
        "--offline-memos",
        action="store_true",
        help="force the deterministic offline debate for memos even if a provider key is set "
        "(reliable, always validator-clean — the default for a shipped showcase)",
    )
    parser.set_defaults(memos=True)
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")

    from rheingold_api.routes import UnderwriteRequest, build_underwrite, get_farm

    con = duckdb.connect(args.mart, read_only=True)
    rows = _candidates(con)
    con.close()
    log.info("%d clean candidates", len(rows))
    chosen = select_showcase(rows)

    from rheingold_agents.providers import provider_name

    provider = provider_name()
    # Memos always bake: an LLM provider is used when present, otherwise the
    # deterministic offline debate (always available, always validator-clean).
    mode = "llm" if provider != "none" else "offline"
    make_memos = args.memos
    log.info("memo generation: %s (mode=%s, provider=%s)", "on" if make_memos else "off", mode, provider)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = []
    memo_ok = 0
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

        gate_flags = _gate_flags(base)
        memo = (
            _try_memo(base, gate_flags, fid, force_offline=args.offline_memos)
            if make_memos
            else _empty_memo()
        )
        if memo["memo_markdown"]:
            memo_ok += 1

        payload = {
            "farm": farm_detail,
            "underwrite": base.model_dump(),
            "presets": presets,
            "gate_flags": [f.model_dump() for f in gate_flags],
            **memo,
        }
        path = out_dir / f"{fid}.json"
        path.write_text(json.dumps(payload))
        ids.append(fid)
        log.info(
            "wrote %s (%.0f kB, memo=%s)",
            path,
            path.stat().st_size / 1024,
            "yes" if memo["memo_markdown"] else "no",
        )

    (out_dir / "index.json").write_text(json.dumps({"showcase_ids": ids}, indent=1))
    log.info("showcase index (%d farms, %d with memos): %s", len(ids), memo_ok, ids)
    if make_memos and memo_ok < len(ids):
        log.info(
            "NOTE: %d/%d memos not generated (provider budget / validation) — those farms show "
            "the degraded memo state; re-run when budget resets or an ANTHROPIC_API_KEY is set",
            len(ids) - memo_ok,
            len(ids),
        )
    return 0


def _empty_memo() -> dict:
    return {"memo_markdown": None, "claims": [], "rebuttals": [], "validation": None}


def _serialise(items) -> list:
    return [i.model_dump() if hasattr(i, "model_dump") else i for i in items]


def _try_memo(base, gate_flags, fid: str, force_offline: bool = False) -> dict:
    """Best-effort memo. LLM provider when present (unless force_offline), else the
    deterministic offline debate. On any failure record null + reason and move on."""
    import asyncio

    from rheingold_agents.offline import memo_to_markdown, run_offline_debate
    from rheingold_agents.orchestrator import run_debate
    from rheingold_agents.providers import provider_name

    try:
        if force_offline or provider_name() == "none":
            out = asyncio.run(run_offline_debate(base.evidence, gate_flags, delay=0))
            markdown = out["memo_markdown"]
        else:
            out = asyncio.run(run_debate(base.evidence, gate_flags))
            memo = out.get("memo")
            markdown = memo_to_markdown(memo) if memo is not None else None
    except Exception as exc:  # noqa: BLE001 — provider errors must never abort the batch
        log.warning("memo generation failed for %s: %s", fid, str(exc)[:200])
        return {
            "memo_markdown": None,
            "claims": [],
            "rebuttals": [],
            "validation": {"ok": False, "errors": [f"generation error: {str(exc)[:200]}"]},
        }
    validation = out.get("validation") or {"ok": False, "errors": ["no validation result"]}
    if not validation.get("ok"):
        log.warning("memo for %s failed validation: %s", fid, validation.get("errors"))
    return {
        "memo_markdown": markdown,
        "claims": _serialise(out.get("claims", [])),
        "rebuttals": _serialise(out.get("rebuttals", [])),
        "validation": validation,
    }


def _gate_flags(result):
    from datetime import datetime

    from rheingold_agents.compliance_gate import run as gate_run

    return gate_run(result, as_of=datetime.now(UTC))


if __name__ == "__main__":
    sys.exit(main())
