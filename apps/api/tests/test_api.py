"""API tests against a tiny SYNTHETIC DuckDB mart (spec §13.1).

Every number in the fixture mart is a clearly-labeled synthetic test value —
NOT market or registry data. Schema follows docs/MART_SCHEMA.md so the API is
exercised against the real contract while the real mart may not exist yet.
"""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient
from rheingold_api import deps, market
from rheingold_api.app import create_app
from rheingold_api.eeg51 import neg_price_rule_hours

SYNTH_YEAR = 2025  # non-leap → 8760 hourly rows
NEG_STREAK_A = range(100, 108)  # 8 consecutive negative hours
NEG_STREAK_B = range(5000, 5003)  # 3 consecutive negative hours
N_NEG_HOURS = len(NEG_STREAK_A) + len(NEG_STREAK_B)


def build_synthetic_mart(db_path: Path) -> None:
    """Write a minimal mart per docs/MART_SCHEMA.md. All values synthetic."""
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE farms (
            farm_id TEXT PRIMARY KEY, name TEXT, lat DOUBLE, lon DOUBLE,
            mw_total DOUBLE, n_units INTEGER, manufacturer TEXT, turbine_type TEXT,
            hub_height_m DOUBLE, rotor_d_m DOUBLE, commissioning_year INTEGER,
            bundesland TEXT, operator TEXT, unit_ids TEXT
        )
        """
    )
    con.execute(
        "INSERT INTO farms VALUES "
        "('wp-synthpark-a', 'Synthpark A (TEST FIXTURE)', 53.5, 8.1, 12.6, 3, "
        " 'TestTurbineWorks', 'TTW-4200', 120.0, 130.0, 2019, 'Niedersachsen', "
        ' \'Test Operator GmbH\', \'["SEE900000000001", "SEE900000000002", "SEE900000000003"]\'), '
        "('wp-synthpark-b', 'Synthpark B no-resource (TEST FIXTURE)', 49.9, 9.2, 8.4, 2, "
        " 'TestTurbineWorks', 'TTW-4200', 110.0, 120.0, 2016, 'Bayern', "
        " 'Test Operator GmbH', '[\"SEE900000000004\", \"SEE900000000005\"]')"
    )
    con.execute(
        """
        CREATE TABLE units (
            unit_id TEXT PRIMARY KEY, farm_name TEXT, lat DOUBLE, lon DOUBLE, mw DOUBLE,
            hub_height_m DOUBLE, rotor_d_m DOUBLE, turbine_type TEXT, manufacturer TEXT,
            commissioning_date DATE, bundesland TEXT, operator TEXT, status TEXT
        )
        """
    )
    for i in (1, 2, 3):
        con.execute(
            "INSERT INTO units VALUES (?, 'Synthpark A (TEST FIXTURE)', 53.5, 8.1, 4.2, "
            "120.0, 130.0, 'TTW-4200', 'TestTurbineWorks', DATE '2019-06-01', "
            "'Niedersachsen', 'Test Operator GmbH', 'In Betrieb')",
            [f"SEE90000000000{i}"],
        )
    # One flat synthetic calendar year of hourly prices with two negative streaks.
    con.execute(
        f"""
        CREATE TABLE prices_hourly AS
        SELECT TIMESTAMP '{SYNTH_YEAR}-01-01 00:00:00' + INTERVAL (i) HOUR AS ts,
               50.0 AS eur_mwh
        FROM range(8760) t(i)
        """
    )
    con.execute(
        f"UPDATE prices_hourly SET eur_mwh = -5.0 WHERE ts >= TIMESTAMP "
        f"'{SYNTH_YEAR}-01-01 00:00:00' + INTERVAL ({NEG_STREAK_A.start}) HOUR AND "
        f"ts < TIMESTAMP '{SYNTH_YEAR}-01-01 00:00:00' + INTERVAL ({NEG_STREAK_A.stop}) HOUR"
    )
    con.execute(
        f"UPDATE prices_hourly SET eur_mwh = -1.0 WHERE ts >= TIMESTAMP "
        f"'{SYNTH_YEAR}-01-01 00:00:00' + INTERVAL ({NEG_STREAK_B.start}) HOUR AND "
        f"ts < TIMESTAMP '{SYNTH_YEAR}-01-01 00:00:00' + INTERVAL ({NEG_STREAK_B.stop}) HOUR"
    )
    # 24 synthetic monthly Marktwerte (2024-01 .. 2025-12).
    con.execute(
        """
        CREATE TABLE marktwerte AS
        SELECT (DATE '2024-01-01' + INTERVAL (i) MONTH)::DATE AS month,
               5.5 AS mw_wind_onshore_ct_kwh
        FROM range(24) t(i)
        """
    )
    con.execute(
        """
        CREATE TABLE resource (
            farm_id TEXT, p50_cf DOUBLE, method TEXT, hub_height_used DOUBLE, source TEXT
        )
        """
    )
    con.execute(
        "INSERT INTO resource VALUES ('wp-synthpark-a', 0.28, 'gwa_windpowerlib', 120.0, "
        "'SYNTHETIC test fixture — not a real resource assessment')"
    )
    con.close()


@pytest.fixture(scope="session")
def mart_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("synthetic_mart")
    build_synthetic_mart(d / "rheingold.duckdb")
    (d / "units_meta.json").write_text(
        json.dumps({"mastr_snapshot_date": "2026-07-01", "note": "SYNTHETIC test fixture"})
    )
    return d


@pytest.fixture()
def client(mart_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RHEINGOLD_MART", str(mart_dir / "rheingold.duckdb"))
    return TestClient(create_app())


@pytest.fixture()
def client_no_mart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RHEINGOLD_MART", str(tmp_path / "does_not_exist.duckdb"))
    return TestClient(create_app())


# ------------------------------------------------------------------ health
def test_health_without_mart_never_500s(client_no_mart: TestClient) -> None:
    r = client_no_mart.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["sha"] == "dev"
    assert body["showcase"] is False
    assert body["data_vintages"] == {
        "prices_max_ts": None,
        "marktwerte_max_month": None,
        "mastr_snapshot": None,
    }


def test_health_with_mart_reports_vintages(client: TestClient) -> None:
    body = client.get("/api/health").json()
    v = body["data_vintages"]
    assert v["prices_max_ts"].startswith(f"{SYNTH_YEAR}-12-31")
    assert v["marktwerte_max_month"] == "2025-12-01"
    assert v["mastr_snapshot"] == "2026-07-01"


# ------------------------------------------------------------------ fleet
def test_fleet_missing_is_actionable_503(client: TestClient) -> None:
    r = client.get("/api/fleet")
    assert r.status_code == 503
    assert "make data" in r.json()["detail"]


def test_fleet_serves_gzip_passthrough(client: TestClient, mart_dir: Path) -> None:
    payload = [{"id": "wp-synthpark-a", "name": "Synthpark A (TEST FIXTURE)", "mw": 12.6}]
    gz = mart_dir / "fleet.json.gz"
    gz.write_bytes(gzip.compress(json.dumps(payload).encode()))
    try:
        r = client.get("/api/fleet")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "public, max-age=86400, immutable"
        assert r.json() == payload  # httpx transparently decodes Content-Encoding: gzip
    finally:
        gz.unlink()


def test_fleet_meta_404_then_passthrough(client: TestClient, mart_dir: Path) -> None:
    assert client.get("/api/fleet/meta").status_code == 404
    meta = mart_dir / "fleet_meta.json"
    meta.write_text(json.dumps({"farm_count": 2, "note": "SYNTHETIC"}))
    try:
        assert client.get("/api/fleet/meta").json()["farm_count"] == 2
    finally:
        meta.unlink()


# ------------------------------------------------------------------ farm dossier
def test_farm_404_is_clear(client: TestClient) -> None:
    r = client.get("/api/farm/wp-nope")
    assert r.status_code == 404
    assert "wp-nope" in r.json()["detail"]


def test_farm_dossier_shape_and_sources(client: TestClient) -> None:
    r = client.get("/api/farm/wp-synthpark-a")
    assert r.status_code == 200
    body = r.json()
    assert body["farm"]["mw_total"] == 12.6
    assert body["resource"]["method"] == "gwa_windpowerlib"
    assert len(body["units"]) == 3
    mastr = [s for s in body["sources"] if s["label"] == "MaStR Registereintrag"]
    assert len(mastr) == 3
    assert all(s["url"] == "https://www.marktstammdatenregister.de/MaStR" for s in mastr)
    assert mastr[0]["unit_id"] == "SEE900000000001"


# ------------------------------------------------------------------ underwrite
def test_underwrite_end_to_end_and_warm_latency(client: TestClient) -> None:
    r = client.post("/api/underwrite", json={"farm_id": "wp-synthpark-a"})
    assert r.status_code == 200, r.text
    body = r.json()
    # scalar presence
    assert body["valuation"]["lcoe_eur_mwh"] > 0
    assert body["valuation"]["breakeven_bid_ct_kwh"] is not None
    assert body["debt"]["min_dscr"] > 0
    assert body["energy"]["p50_gwh"] > 0
    assert len(body["annual"]["year"]) == body["assumptions"]["lifetime_years"]
    # vintage + cohort wiring: 2019 vintage row, 2019 → §51 six-hour rule
    assert body["assumptions"]["capex_eur_per_mw"] == 1_430_000
    assert body["assumptions"]["interest_rate"] == 0.023
    assert body["assumptions"]["neg_price_rule_hours"] == 6
    # method sigma: gwa_windpowerlib → 0.09
    assert body["farm"]["cf_uncertainty_sigma"] == 0.09
    # warm call latency (< 1.5 s; MarketInputs cache is hot now)
    t0 = time.perf_counter()
    r2 = client.post("/api/underwrite", json={"farm_id": "wp-synthpark-a"})
    warm = time.perf_counter() - t0
    assert r2.status_code == 200
    assert warm < 1.5, f"warm underwrite took {warm:.2f}s"


def test_underwrite_overrides_and_shocks_apply(client: TestClient) -> None:
    r = client.post(
        "/api/underwrite",
        json={
            "farm_id": "wp-synthpark-a",
            "assumptions_overrides": {"anzulegender_wert_ct_kwh": 6.5},
            "shocks": {"price_level": -0.2},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assumptions"]["anzulegender_wert_ct_kwh"] == 6.5
    assert body["shocks"]["price_level"] == -0.2


def test_underwrite_missing_resource_422_names_pipeline(client: TestClient) -> None:
    r = client.post("/api/underwrite", json={"farm_id": "wp-synthpark-b"})
    assert r.status_code == 422
    assert "resource" in r.json()["detail"].lower()


def test_underwrite_unknown_override_422(client: TestClient) -> None:
    r = client.post(
        "/api/underwrite",
        json={"farm_id": "wp-synthpark-a", "assumptions_overrides": {"nonsense_knob": 1}},
    )
    assert r.status_code == 422
    assert "nonsense_knob" in r.json()["detail"]


# ------------------------------------------------------------------ market charts
def test_market_chart_payload_shape(client: TestClient) -> None:
    r = client.get("/api/market", params={"farm_id": "wp-synthpark-a"})
    assert r.status_code == 200
    body = r.json()
    assert body["representative_year"] == SYNTH_YEAR
    assert len(body["daily"]) == 365
    assert body["daily"][0] == {"t": f"{SYNTH_YEAR}-01-01", "v": 50.0}
    assert len(body["marktwerte"]) == 24
    assert body["marktwerte"][0] == {"t": "2024-01-01", "v": 5.5}
    assert body["neg_hours_by_year"] == [{"year": SYNTH_YEAR, "hours": N_NEG_HOURS}]


# ------------------------------------------------------------------ memo SSE
def test_memo_without_api_key_streams_error_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with client.stream("POST", "/api/memo", json={"farm_id": "wp-synthpark-a"}) as r:
        assert r.status_code == 200
        body = "".join(chunk for chunk in r.iter_text())
    assert "event: error" in body
    assert "ANTHROPIC_API_KEY" in body


# ------------------------------------------------------------------ backtest
def test_backtest_missing_points_at_make_backtest(client: TestClient) -> None:
    r = client.get("/api/backtest")
    assert r.status_code == 503
    assert "make backtest" in r.json()["detail"]


# ------------------------------------------------------------------ eeg51 unit map
@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2010, 8760),
        (2015, 8760),
        (2016, 6),
        (2020, 6),
        (2021, 4),
        (2022, 4),
        (2023, 1),
        (2024, 1),
        (2025, 0),
        (2030, 0),
    ],
)
def test_neg_price_rule_cohorts(year: int, expected: int) -> None:
    assert neg_price_rule_hours(year) == expected


@pytest.fixture(autouse=True)
def _reset_caches() -> None:
    """Connections + MarketInputs cache are keyed on paths; keep tests independent."""
    yield
    market.reset_cache()
    deps.reset_connections()
