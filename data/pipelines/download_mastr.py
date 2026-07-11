"""MaStR onshore wind fleet (open-mastr bulk) -> mart/units.parquet.

Downloads the Marktstammdatenregister bulk export via open-mastr 0.17.x
(partial HTTP-range download of the wind + market XML from the daily
Gesamtdatenexport zip, ~verified surface), lands a sqlite DB under
data/raw/mastr/, then extracts the onshore in-operation fleet per
docs/MART_SCHEMA.md `units`.

Verified column facts (2026-07-11, open-mastr 0.17.1):
- wind table is `wind_extended`; PK `EinheitMastrNummer`.
- onshore filter: `WindAnLandOderAufSee = 'Windkraft an Land'` — the legacy
  `Lage` column is 100% NULL in current exports, do NOT use it.
- status: `EinheitBetriebsstatus = 'In Betrieb'`.
- `Hersteller` holds the manufacturer NAME after bulk cleansing.
- operator name: join `AnlagenbetreiberMastrNummer` -> `market_actors.MastrNummer`
  (Firmenname, fallback Vor-/Nachname for natural persons).
- `Nettonennleistung` is in kW (/1000 -> MW).

License: DL-DE/BY-2.0. Attribution: Marktstammdatenregister, Bundesnetzagentur.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "mastr"
MART_PATH = REPO_ROOT / "data" / "mart" / "units.parquet"
META_PATH = REPO_ROOT / "data" / "mart" / "units_meta.json"
SQLITE_PATH = RAW_DIR / "data" / "sqlite" / "open-mastr.db"
XML_DOWNLOAD_DIR = RAW_DIR / "data" / "xml_download"

# Germany bounding box (generous, incl. islands): used only for QA reporting.
DE_BBOX = {"lat_min": 47.2, "lat_max": 55.1, "lon_min": 5.8, "lon_max": 15.1}

# market_actors (operator names) is optional: the full market download spans most
# of the export's 58 files and can take hours on a throttled server; wind-only is
# minutes. Run with --with-market to backfill operator names.
REQUIRED_TABLES = ("wind_extended",)

_SELECT_COMMON = """
    we.EinheitMastrNummer       AS unit_id,
    we.NameWindpark             AS farm_name,
    we.Breitengrad              AS lat,
    we.Laengengrad              AS lon,
    we.Nettonennleistung / 1000.0 AS mw,
    we.Nabenhoehe               AS hub_height_m,
    we.Rotordurchmesser         AS rotor_d_m,
    we.Typenbezeichnung         AS turbine_type,
    we.Hersteller               AS manufacturer,
    we.Inbetriebnahmedatum      AS commissioning_date,
    we.Bundesland               AS bundesland,
    {operator_expr}             AS operator,
    we.EinheitBetriebsstatus    AS status
FROM wind_extended AS we
{join}
WHERE we.WindAnLandOderAufSee = 'Windkraft an Land'
  AND we.EinheitBetriebsstatus = 'In Betrieb'
  AND we.Breitengrad IS NOT NULL
  AND we.Laengengrad IS NOT NULL
"""

QUERY_WITH_MARKET = "SELECT" + _SELECT_COMMON.format(
    operator_expr=(
        "COALESCE(ma.Firmenname, NULLIF(TRIM(COALESCE(ma.MarktakteurVorname, '') || ' ' "
        "|| COALESCE(ma.MarktakteurNachname, '')), ''))"
    ),
    join="LEFT JOIN market_actors AS ma ON ma.MastrNummer = we.AnlagenbetreiberMastrNummer",
)
QUERY_WIND_ONLY = "SELECT" + _SELECT_COMMON.format(operator_expr="NULL", join="")

log = logging.getLogger("download_mastr")


def sqlite_has_tables(db_path: Path) -> bool:
    """True if the cached sqlite DB has non-empty wind_extended and market_actors."""
    if not db_path.exists():
        return False
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            names = {
                r[0]
                for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if not set(REQUIRED_TABLES) <= names:
                return False
            for table in REQUIRED_TABLES:
                (n,) = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
                if n == 0:
                    return False
            return True
        finally:
            con.close()
    except sqlite3.Error as exc:
        log.warning("cached sqlite unreadable (%s) — will re-download", exc)
        return False


def download_bulk(with_market: bool) -> None:
    """Run the open-mastr bulk download into RAW_DIR."""
    os.environ["OUTPUT_PATH"] = str(RAW_DIR)
    from open_mastr import Mastr  # import after OUTPUT_PATH is set

    data = ["wind", "market"] if with_market else ["wind"]
    log.info("downloading MaStR bulk export (%s) via open-mastr ...", "+".join(data))
    db = Mastr()
    db.download(data=data, bulk_cleansing=True)
    if not sqlite_has_tables(SQLITE_PATH):
        raise RuntimeError(
            f"open-mastr download finished but {SQLITE_PATH} is missing required "
            f"non-empty tables {REQUIRED_TABLES}. Not writing any output."
        )


def snapshot_date() -> str:
    """Snapshot date from the downloaded Gesamtdatenexport zip name, else DatumDownload."""
    if XML_DOWNLOAD_DIR.exists():
        dates = []
        for p in XML_DOWNLOAD_DIR.glob("Gesamtdatenexport_*.zip"):
            m = re.search(r"(\d{8})", p.name)
            if m:
                dates.append(m.group(1))
        if dates:
            d = max(dates)
            return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    con = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT MAX(DatumDownload) FROM wind_extended").fetchone()
    finally:
        con.close()
    if row and row[0]:
        return str(row[0])[:10]
    return dt.date.today().isoformat()


def _has_market_actors(con: sqlite3.Connection) -> bool:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='market_actors'"
    ).fetchall()
    if not rows:
        return False
    (n,) = con.execute("SELECT COUNT(*) FROM market_actors").fetchone()
    return n > 0


def extract_units() -> pd.DataFrame:
    con = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
    try:
        if _has_market_actors(con):
            df = pd.read_sql_query(QUERY_WITH_MARKET, con)
        else:
            log.info("market_actors absent — operator column will be NULL (see --with-market)")
            df = pd.read_sql_query(QUERY_WIND_ONLY, con)
    finally:
        con.close()
    if df.empty:
        raise RuntimeError("query returned 0 onshore in-operation units — refusing to write")

    n0 = len(df)
    df = df.drop_duplicates(subset="unit_id", keep="first")
    if len(df) != n0:
        log.info("dropped %d duplicate unit ids", n0 - len(df))

    # Non-null contract: unit_id, lat, lon, mw, status.
    for col in ("unit_id", "lat", "lon", "mw", "status"):
        n_null = int(df[col].isna().sum())
        if n_null:
            raise RuntimeError(f"column {col!r} has {n_null} NULLs — schema forbids this")

    df["commissioning_date"] = pd.to_datetime(df["commissioning_date"], errors="raise").dt.date
    df = df.astype(
        {
            "unit_id": "string",
            "farm_name": "string",
            "lat": "float64",
            "lon": "float64",
            "mw": "float64",
            "hub_height_m": "float64",
            "rotor_d_m": "float64",
            "turbine_type": "string",
            "manufacturer": "string",
            "bundesland": "string",
            "operator": "string",
            "status": "string",
        }
    )
    return df.sort_values("unit_id").reset_index(drop=True)


def qa_report(df: pd.DataFrame) -> None:
    total_mw = df["mw"].sum()
    log.info("units: %d, total: %.1f MW (%.2f GW)", len(df), total_mw, total_mw / 1000)
    if not 20_000 <= len(df) <= 40_000:
        raise RuntimeError(f"unit count {len(df)} outside plausible 20k-40k range")
    if not 50_000 <= total_mw <= 90_000:
        raise RuntimeError(f"total MW {total_mw:.0f} outside plausible 50-90 GW range")

    inside = df["lat"].between(DE_BBOX["lat_min"], DE_BBOX["lat_max"]) & df["lon"].between(
        DE_BBOX["lon_min"], DE_BBOX["lon_max"]
    )
    n_out = int((~inside).sum())
    log.info(
        "coords inside DE bbox: %d/%d (%.3f%%), %d outliers",
        int(inside.sum()),
        len(df),
        100 * inside.mean(),
        n_out,
    )
    if n_out:
        log.info(
            "outlier sample:\n%s",
            df.loc[~inside, ["unit_id", "lat", "lon", "bundesland"]].head(10).to_string(),
        )
    if inside.mean() < 0.99:
        raise RuntimeError(f"only {100 * inside.mean():.2f}% of coords inside Germany bbox")

    log.info("Bundesland top 5:\n%s", df["bundesland"].value_counts().head(5).to_string())
    log.info("manufacturer top 10:\n%s", df["manufacturer"].value_counts().head(10).to_string())
    log.info(
        "commissioning_date range: %s .. %s (%d null)",
        df["commissioning_date"].min(),
        df["commissioning_date"].max(),
        int(df["commissioning_date"].isna().sum()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="force a fresh MaStR bulk download even if the cached sqlite exists",
    )
    parser.add_argument(
        "--with-market",
        action="store_true",
        help="also download market-actor tables for operator names (slow: most of the export)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if args.refresh or not sqlite_has_tables(SQLITE_PATH):
        download_bulk(with_market=args.with_market)
    else:
        log.info("using cached sqlite at %s (pass --refresh to re-download)", SQLITE_PATH)

    df = extract_units()
    qa_report(df)

    MART_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(MART_PATH, index=False)
    log.info("wrote %s (%d rows)", MART_PATH, len(df))

    meta = {
        "snapshot_date": snapshot_date(),
        "n_units": int(len(df)),
        "total_mw": round(float(df["mw"].sum()), 3),
        "license": "DL-DE/BY-2.0",
        "attribution": "Marktstammdatenregister, Bundesnetzagentur (DL-DE/BY-2.0)",
    }
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n")
    log.info("wrote %s: %s", META_PATH, meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
