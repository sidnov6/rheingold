"""Download SMARD day-ahead hourly prices (DE/LU, filter 4169) into the mart.

Source: https://www.smard.de/app/chart_data/4169/DE/index_hour.json (weekly
chunks keyed at Monday 00:00 Europe/Berlin, epoch ms). License: CC BY 4.0,
attribution "Bundesnetzagentur | SMARD.de".

Outputs:
  data/mart/prices_hourly.parquet  (ts TIMESTAMP naive-UTC, eur_mwh DOUBLE)
  data/mart/prices_meta.json
Raw weekly JSON chunks are cached under data/raw/smard/ and only the latest
two chunks are re-downloaded on re-runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

FILTER_ID = 4169
REGION = "DE"
RESOLUTION = "hour"
BASE = f"https://www.smard.de/app/chart_data/{FILTER_ID}/{REGION}"
INDEX_URL = f"{BASE}/index_{RESOLUTION}.json"
DATA_URL = f"{BASE}/{FILTER_ID}_{REGION}_{RESOLUTION}_{{ts}}.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_INTERVAL_S = 0.5  # <= 2 req/s
PLAUSIBLE_MIN, PLAUSIBLE_MAX = -500.0, 4000.0

_last_request_at = 0.0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def polite_get(session: requests.Session, url: str, retries: int = 5) -> requests.Response:
    """GET with rate limiting and exponential backoff on 5xx."""
    global _last_request_at
    for attempt in range(retries):
        wait = REQUEST_INTERVAL_S - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()
        resp = session.get(url, timeout=60)
        if resp.status_code >= 500:
            backoff = 2.0**attempt
            log(f"  HTTP {resp.status_code} for {url}, retrying in {backoff:.0f}s")
            time.sleep(backoff)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"SMARD returned 5xx {retries} times for {url}")


def fetch_index(session: requests.Session) -> list[int]:
    log(f"Fetching index {INDEX_URL}")
    timestamps = polite_get(session, INDEX_URL).json()["timestamps"]
    if not timestamps:
        raise RuntimeError("SMARD index returned no timestamps")
    return sorted(timestamps)


def fetch_chunk(session: requests.Session, ts: int, raw_dir: Path, force: bool) -> dict:
    """Fetch one weekly chunk, using the on-disk cache unless force=True."""
    cache = raw_dir / f"{FILTER_ID}_{REGION}_{RESOLUTION}_{ts}.json"
    if cache.exists() and not force:
        return json.loads(cache.read_text())
    resp = polite_get(session, DATA_URL.format(ts=ts))
    payload = resp.json()
    if "series" not in payload:
        raise RuntimeError(f"Chunk {ts}: no 'series' key in response")
    tmp = cache.with_suffix(".json.tmp")
    tmp.write_text(resp.text)
    tmp.replace(cache)
    return payload


def build_frame(chunks: list[dict]) -> pd.DataFrame:
    rows = [pair for chunk in chunks for pair in chunk["series"] if pair[1] is not None]
    if not rows:
        raise RuntimeError("No non-null price observations found")
    df = pd.DataFrame(rows, columns=["ts_ms", "eur_mwh"])
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.tz_localize(None)
    df = (
        df[["ts", "eur_mwh"]]
        .astype({"eur_mwh": "float64"})
        .drop_duplicates(subset="ts")
        .sort_values("ts")
        .reset_index(drop=True)
    )
    return df


def verify(df: pd.DataFrame) -> None:
    if df["ts"].isna().any() or df["eur_mwh"].isna().any():
        raise RuntimeError("Nulls present in ts or eur_mwh")
    if not df["ts"].is_unique:
        raise RuntimeError("Duplicate timestamps present")
    lo, hi = df["eur_mwh"].min(), df["eur_mwh"].max()
    if lo < PLAUSIBLE_MIN or hi > PLAUSIBLE_MAX:
        raise RuntimeError(f"Prices outside plausible range: min={lo}, max={hi}")
    gaps = df["ts"].diff().dropna()
    bad = gaps[gaps != pd.Timedelta(hours=1)]
    if len(bad) > 0:
        raise RuntimeError(
            f"{len(bad)} non-hourly gaps in UTC series, first at {df['ts'].iloc[bad.index[0]]}"
        )
    log(
        "Verification: hourly-continuous in UTC, no nulls, no duplicates, "
        f"range [{lo:.2f}, {hi:.2f}] EUR/MWh"
    )

    log("\nYearly stats (mean/min/max EUR/MWh, hours, negative hours):")
    yearly = df.assign(year=df["ts"].dt.year).groupby("year")["eur_mwh"]
    stats = yearly.agg(["mean", "min", "max", "count"])
    stats["neg_hours"] = yearly.apply(lambda s: int((s < 0).sum()))
    print(stats.round(2).to_string(), file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--raw-dir", type=Path, default=root / "data" / "raw" / "smard")
    parser.add_argument("--mart-dir", type=Path, default=root / "data" / "mart")
    args = parser.parse_args()

    args.raw_dir.mkdir(parents=True, exist_ok=True)
    args.mart_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    index = fetch_index(session)
    log(f"Index has {len(index)} weekly chunks: {index[0]} .. {index[-1]}")

    latest_two = set(index[-2:])
    chunks: list[dict] = []
    n_fetched = 0
    for i, ts in enumerate(index):
        force = ts in latest_two
        cached = (args.raw_dir / f"{FILTER_ID}_{REGION}_{RESOLUTION}_{ts}.json").exists()
        chunks.append(fetch_chunk(session, ts, args.raw_dir, force=force))
        if force or not cached:
            n_fetched += 1
        if (i + 1) % 50 == 0 or i + 1 == len(index):
            log(f"  {i + 1}/{len(index)} chunks ready ({n_fetched} downloaded)")

    df = build_frame(chunks)
    verify(df)

    out = args.mart_dir / "prices_hourly.parquet"
    df.to_parquet(out, index=False)
    log(f"\nWrote {out}: {len(df)} rows, {df['ts'].min()} .. {df['ts'].max()} UTC")

    meta = {
        "source": "SMARD chart_data API, filter 4169 (day-ahead price DE/LU), "
        "https://www.smard.de/app/chart_data/4169/DE/",
        "license": "CC BY 4.0",
        "attribution": "Bundesnetzagentur | SMARD.de",
        "retrieved_at": dt.datetime.now(dt.UTC).isoformat(),
        "first_ts": df["ts"].min().isoformat(),
        "last_ts": df["ts"].max().isoformat(),
        "n_hours": int(len(df)),
    }
    meta_path = args.mart_dir / "prices_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    log(f"Wrote {meta_path}")


if __name__ == "__main__":
    main()
