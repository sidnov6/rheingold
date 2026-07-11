"""Netztransparenz monthly Marktwerte (MW Wind an Land) -> mart/marktwerte.parquet.

Primary path (no auth): the Marktwertuebersicht page's chart backend, an
unauthenticated JSON POST per calendar year to the DNN HighchartService.
Fallback path (documented, OAuth2): ds.netztransparenz.de WebAPI, requires
NETZTRANSPARENZ_CLIENT_ID / NETZTRANSPARENZ_CLIENT_SECRET env vars.

Output schema (docs/MART_SCHEMA.md): month DATE (first of month),
mw_wind_onshore_ct_kwh DOUBLE. Series starts 2012-01, unit ct/kWh.

Attribution: "Quelle: netztransparenz.de".
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "netztransparenz"
MART_PATH = REPO_ROOT / "data" / "mart" / "marktwerte.parquet"
META_PATH = REPO_ROOT / "data" / "mart" / "marktwerte_meta.json"

CHART_URL = (
    "https://www.netztransparenz.de/DesktopModules/LotesCharts/Services/"
    "HighchartService.asmx/GetMarketpremiumData"
)
PAGE_URL = (
    "https://www.netztransparenz.de/de-de/Erneuerbare-Energien-und-Umlagen/"
    "EEG/Transparenzanforderungen/Marktpr%C3%A4mie/Marktwert%C3%BCbersicht"
)
OAUTH_TOKEN_URL = "https://identity.netztransparenz.de/users/connect/token"
API_MARKTPRAEMIE_URL = (
    "https://ds.netztransparenz.de/api/v1/data/marktpraemie/"
    "{year_from}/{month_from}/{year_to}/{month_to}"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

FIRST_YEAR = 2012
# Row labels used in gridData: 2012-2020 vs 2021+.
WIND_ONSHORE_LABELS = {"MW Wind an Land", "MW Wind Onshore"}

# Known-good values (live-verified 2026-07-11, cross-checked against the
# official API doc Format-12 examples and the DGS newsletter). Hard-fail
# on mismatch: a silent parser drift is worse than a loud crash.
CROSSCHECK = {
    "2012-01-01": 3.519,
    "2024-01-01": 6.502,
    "2025-11-01": 8.930,
}

MIN_REQUEST_INTERVAL_S = 1.0  # <= 1 req/s (site WAF limit is 2 req/s)

log = logging.getLogger("marktwerte")


class SourceError(RuntimeError):
    """Raised when the upstream source fails or returns unparseable data."""


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": PAGE_URL,
        }
    )
    return session


_last_request_ts = 0.0


def _throttle() -> None:
    global _last_request_ts
    wait = _last_request_ts + MIN_REQUEST_INTERVAL_S - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def request_with_retry(
    session: requests.Session, method: str, url: str, *, max_tries: int = 5, **kwargs
) -> requests.Response:
    backoff = 2.0
    for attempt in range(1, max_tries + 1):
        _throttle()
        try:
            resp = session.request(method, url, timeout=60, **kwargs)
        except requests.RequestException as exc:
            if attempt == max_tries:
                raise SourceError(f"{method} {url} failed after {max_tries} tries: {exc}") from exc
            log.warning(
                "attempt %d/%d failed (%s); retrying in %.0fs", attempt, max_tries, exc, backoff
            )
            time.sleep(backoff)
            backoff *= 2
            continue
        if resp.status_code >= 500 or resp.status_code == 429:
            if attempt == max_tries:
                raise SourceError(
                    f"{method} {url} -> HTTP {resp.status_code} after {max_tries} tries"
                )
            log.warning(
                "HTTP %d on attempt %d/%d; retrying in %.0fs",
                resp.status_code,
                attempt,
                max_tries,
                backoff,
            )
            time.sleep(backoff)
            backoff *= 2
            continue
        if not resp.ok:
            raise SourceError(f"{method} {url} -> HTTP {resp.status_code}: {resp.text[:300]}")
        return resp
    raise SourceError(f"{method} {url}: retry loop exhausted")  # unreachable


# ---------------------------------------------------------------------------
# Primary path: unauthenticated chart-service POST, one call per year
# ---------------------------------------------------------------------------


def fetch_year_raw(session: requests.Session, year: int, *, force: bool) -> str:
    """Return the raw JSON response body for one year, using the on-disk cache.

    Completed historical years are immutable and never re-fetched; the
    current year is always re-fetched (new months appear monthly).
    """
    cache_path = RAW_DIR / f"marketpremium_{year}.json"
    is_historical = year < dt.date.today().year
    if cache_path.exists() and is_historical and not force:
        log.info("year %d: using cached %s", year, cache_path.name)
        return cache_path.read_text(encoding="utf-8")

    body = {
        "dateFrom": f"{year}-01-01T00:00:00",
        "asImage": False,
        "diagramType": "line",
        "highChartType": "2",
        "columnColors": None,
        "template": "",
        "title": "Monatsmarktwerte",
        "timezone": "Europe/Berlin",
    }
    log.info("year %d: POST %s", year, CHART_URL)
    resp = request_with_retry(
        session,
        "POST",
        CHART_URL,
        json=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    text = resp.text
    # Validate before caching so a broken response never poisons the cache.
    parse_year_grid(text, year)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text, encoding="utf-8")
    return text


def _parse_german_float(cell: str) -> float | None:
    cell = cell.strip()
    if not cell or cell in {"-", "n/a"}:
        return None
    try:
        return float(cell.replace(".", "").replace(",", "."))
    except ValueError as exc:
        raise SourceError(f"unparseable numeric cell {cell!r}") from exc


def parse_year_grid(raw_body: str, year: int) -> dict[dt.date, float]:
    """Parse one year's chart-service response into {first-of-month: ct/kWh}."""
    try:
        outer = json.loads(raw_body)
        inner = json.loads(outer["d"])
        grid = inner["gridData"]
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceError(
            f"year {year}: unexpected response structure "
            f"(expected {{'d': <json with gridData>}}): {exc}; body head: {raw_body[:200]!r}"
        ) from exc

    rows = list(csv.reader(io.StringIO(grid), delimiter=";"))
    wind_rows = [r for r in rows if r and r[0].strip() in WIND_ONSHORE_LABELS]
    if len(wind_rows) != 1:
        labels = [r[0] for r in rows if r]
        raise SourceError(
            f"year {year}: expected exactly one wind-onshore row in gridData, "
            f"found {len(wind_rows)}; row labels: {labels}"
        )
    row = wind_rows[0]
    if len(row) != 13:
        raise SourceError(
            f"year {year}: wind row has {len(row)} columns, expected 13 (label + 12 months)"
        )

    values: dict[dt.date, float] = {}
    for month_idx, cell in enumerate(row[1:], start=1):
        value = _parse_german_float(cell)
        if value is not None:
            values[dt.date(year, month_idx, 1)] = value
    return values


def fetch_via_chart_service(start_year: int, end_year: int, *, force: bool) -> dict[dt.date, float]:
    session = make_session()
    series: dict[dt.date, float] = {}
    for year in range(start_year, end_year + 1):
        raw = fetch_year_raw(session, year, force=force)
        year_values = parse_year_grid(raw, year)
        if not year_values and year < end_year:
            raise SourceError(f"year {year}: no monthly values parsed for a historical year")
        log.info("year %d: %d monthly values", year, len(year_values))
        series.update(year_values)
    return series


# ---------------------------------------------------------------------------
# Fallback path: documented OAuth2 WebAPI (Format-12 CSV)
# ---------------------------------------------------------------------------


def fetch_via_oauth_api(start_year: int, end_year: int) -> dict[dt.date, float]:
    client_id = os.environ.get("NETZTRANSPARENZ_CLIENT_ID")
    client_secret = os.environ.get("NETZTRANSPARENZ_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SourceError(
            "OAuth fallback requires NETZTRANSPARENZ_CLIENT_ID and "
            "NETZTRANSPARENZ_CLIENT_SECRET environment variables "
            "(register at https://api-portal.netztransparenz.de/)"
        )
    session = make_session()
    token_resp = request_with_retry(
        session,
        "POST",
        OAUTH_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    token = token_resp.json().get("access_token")
    if not token:
        raise SourceError(f"token endpoint returned no access_token: {token_resp.text[:300]}")

    url = API_MARKTPRAEMIE_URL.format(
        year_from=start_year, month_from=1, year_to=end_year, month_to=12
    )
    resp = request_with_retry(session, "GET", url, headers={"Authorization": f"Bearer {token}"})
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / f"api_marktpraemie_{start_year}_{end_year}.csv").write_text(
        resp.text, encoding="utf-8"
    )

    # Format 12: "Monat;MW-EPEX in ct/kWh;MW Wind Onshore in ct/kWh;..."
    rows = list(csv.reader(io.StringIO(resp.text), delimiter=";"))
    if not rows:
        raise SourceError("OAuth API returned an empty CSV")
    header = [h.strip() for h in rows[0]]
    try:
        col = header.index("MW Wind Onshore in ct/kWh")
    except ValueError as exc:
        raise SourceError(
            f"'MW Wind Onshore in ct/kWh' column not found in header: {header}"
        ) from exc

    series: dict[dt.date, float] = {}
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        month_str, year_str = row[0].strip().split("/")  # e.g. "1/2024"
        value = _parse_german_float(row[col])
        if value is not None:
            series[dt.date(int(year_str), int(month_str), 1)] = value
    return series


# ---------------------------------------------------------------------------
# Validation + output
# ---------------------------------------------------------------------------


def validate(series: dict[dt.date, float]) -> None:
    if not series:
        raise SourceError("empty series")

    for iso, expected in CROSSCHECK.items():
        month = dt.date.fromisoformat(iso)
        got = series.get(month)
        if got is None or abs(got - expected) > 1e-9:
            raise SourceError(
                f"cross-check FAILED for {iso}: expected {expected}, got {got} "
                "— parser drift or upstream data change; refusing to write output"
            )
        log.info("cross-check ok: %s = %.3f ct/kWh", iso, expected)

    months = sorted(series)
    if months[0] != dt.date(FIRST_YEAR, 1, 1):
        raise SourceError(f"series starts {months[0]}, expected {FIRST_YEAR}-01-01")
    cursor = months[0]
    for month in months:
        if month != cursor:
            raise SourceError(f"gap in series: expected {cursor}, next available is {month}")
        cursor = dt.date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)

    bad = {m: v for m, v in series.items() if not (0.0 < v < 100.0)}
    if bad:
        raise SourceError(f"implausible ct/kWh values: {bad}")


def write_outputs(series: dict[dt.date, float], source_path: str) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "month": pd.to_datetime(sorted(series)),
            "mw_wind_onshore_ct_kwh": [series[m] for m in sorted(series)],
        }
    )
    frame["month"] = frame["month"].dt.date  # DATE, not TIMESTAMP
    MART_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(MART_PATH, index=False)

    months = sorted(series)
    meta = {
        "source_url": source_path,
        "page_url": PAGE_URL,
        "license_note": (
            "no explicit open-data license; statutory EEG transparency "
            "publication; attribution 'Quelle: netztransparenz.de'"
        ),
        "retrieved_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "coverage": {
            "first_month": months[0].isoformat(),
            "last_month": months[-1].isoformat(),
            "n_months": len(months),
        },
        "unit": "ct/kWh",
    }
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Netztransparenz monthly Marktwerte (MW Wind an Land) to parquet."
    )
    parser.add_argument("--start-year", type=int, default=FIRST_YEAR)
    parser.add_argument("--end-year", type=int, default=dt.date.today().year)
    parser.add_argument("--force", action="store_true", help="re-download cached historical years")
    parser.add_argument(
        "--use-oauth-api",
        action="store_true",
        help="use the documented OAuth2 WebAPI instead of the chart service "
        "(requires NETZTRANSPARENZ_CLIENT_ID/SECRET)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if args.use_oauth_api:
        series = fetch_via_oauth_api(args.start_year, args.end_year)
        source = API_MARKTPRAEMIE_URL
    else:
        series = fetch_via_chart_service(args.start_year, args.end_year, force=args.force)
        source = CHART_URL

    validate(series)
    frame = write_outputs(series, source)

    log.info(
        "wrote %s: %d rows, %s .. %s",
        MART_PATH,
        len(frame),
        frame["month"].min(),
        frame["month"].max(),
    )
    yearly = frame.assign(year=pd.to_datetime(frame["month"]).dt.year).groupby("year")[
        "mw_wind_onshore_ct_kwh"
    ]
    for year, mean in yearly.mean().items():
        n_months = yearly.count()[year]
        log.info("  %d: avg %.3f ct/kWh over %d months", year, mean, n_months)
    return 0


if __name__ == "__main__":
    sys.exit(main())
