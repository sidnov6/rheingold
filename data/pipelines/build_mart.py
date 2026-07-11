"""Assemble data/mart/rheingold.duckdb from the mart parquet files. Spec §7.

Loads every parquet that exists (units, farms, prices_hourly, marktwerte,
resource, cf_hourly) with CREATE OR REPLACE TABLE — idempotent, safe to re-run
after any single pipeline. Missing parquets are skipped with a stderr note so
the mart can be built incrementally while upstream downloads are still running.

Also creates a `vintages` view: one row per loaded table with its row count and
max timestamp/month (NULL for tables without a time column) — the API's
freshness endpoint reads this.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
MART_DIR = REPO_ROOT / "data" / "mart"
DB_PATH = MART_DIR / "rheingold.duckdb"

# (table name, parquet filename, time column for the vintages view or None)
TABLES: tuple[tuple[str, str, str | None], ...] = (
    ("units", "units.parquet", None),
    ("farms", "farms.parquet", None),
    ("prices_hourly", "prices_hourly.parquet", "ts"),
    ("marktwerte", "marktwerte.parquet", "month"),
    ("resource", "resource.parquet", None),
    ("cf_hourly", "cf_hourly.parquet", "ts"),
)

log = logging.getLogger("build_mart")


def build(db_path: Path, mart_dir: Path) -> list[str]:
    """Create/refresh the DuckDB mart; returns the list of loaded table names."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    loaded: list[tuple[str, str | None]] = []
    con = duckdb.connect(str(db_path))
    try:
        for table, filename, ts_col in TABLES:
            path = mart_dir / filename
            if not path.exists():
                print(f"note: {path} missing — skipping table {table!r}", file=sys.stderr)
                continue
            con.execute(
                f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_parquet(?)",  # noqa: S608
                [str(path)],
            )
            (n,) = con.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
            log.info("table %s: %d rows (from %s)", table, n, filename)
            loaded.append((table, ts_col))

        if not loaded:
            raise RuntimeError(f"no mart parquet files found in {mart_dir} — nothing to build")

        selects = []
        for table, ts_col in loaded:
            max_expr = f"CAST(max({ts_col}) AS VARCHAR)" if ts_col else "CAST(NULL AS VARCHAR)"
            selects.append(
                f"SELECT '{table}' AS table_name, count(*) AS n_rows, "
                f"{max_expr} AS max_ts FROM {table}"
            )
        con.execute("CREATE OR REPLACE VIEW vintages AS " + " UNION ALL ".join(selects))
        for row in con.execute("SELECT * FROM vintages ORDER BY table_name").fetchall():
            log.info("vintages: %-14s n_rows=%-9d max_ts=%s", row[0], row[1], row[2])
    finally:
        con.close()
    return [t for t, _ in loaded]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--mart-dir", type=Path, default=MART_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    loaded = build(args.db, args.mart_dir)
    log.info("wrote %s with tables: %s", args.db, ", ".join(loaded))
    return 0


if __name__ == "__main__":
    sys.exit(main())
