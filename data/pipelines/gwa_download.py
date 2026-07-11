"""Download the Global Wind Atlas 4.0 mean wind speed GeoTIFF for Germany at 100 m.

Source: https://globalwindatlas.info/api/gis/country/DEU/wind-speed/100
(302 -> https://gwa.cdn.nazkamapps.com/country_tifs_v4/DEU_wind-speed_100m.tif,
~30.6 MB, GWA 4.0, DTU, license CC BY 4.0).

Idempotent: skips the download if the target file already exists and opens as a
valid raster covering the Germany bounding box. Never fabricates data: any
download or validation failure raises with a clear message.

Spec: docs/RHEINGOLD_BUILD_SPEC.md §7.4 (Path B).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio
import requests

GWA_URL = "https://globalwindatlas.info/api/gis/country/DEU/wind-speed/100"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "raw" / "gwa" / "DEU_wind-speed_100m.tif"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 rheingold-pipeline/0.1"
)
# Germany bbox (lon_min, lat_min, lon_max, lat_max) — raster must cover this.
# Approximate; the GWA country tif is clipped near the border (actual German
# territory extremes: ~5.87E, 47.27N, 15.04E, 55.06N), so allow a small slack.
GERMANY_BBOX = (5.8, 47.2, 15.1, 55.1)
BBOX_TOL_DEG = 0.1
MIN_EXPECTED_BYTES = 10_000_000  # sanity floor; real file is ~30.6 MB


def log(msg: str) -> None:
    print(f"[gwa_download] {msg}", file=sys.stderr, flush=True)


def download(url: str, dest: Path, retries: int = 4) -> None:
    """Stream-download url to dest atomically, retrying on 5xx with backoff."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            log(f"GET {url} (attempt {attempt}/{retries})")
            with requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                stream=True,
                timeout=120,
                allow_redirects=True,
            ) as resp:
                if resp.status_code >= 500:
                    raise requests.HTTPError(f"server error {resp.status_code}", response=resp)
                resp.raise_for_status()
                with tempfile.NamedTemporaryFile(
                    dir=dest.parent, suffix=".part", delete=False
                ) as tmp:
                    tmp_path = Path(tmp.name)
                    n = 0
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        tmp.write(chunk)
                        n += len(chunk)
                log(f"downloaded {n:,} bytes")
                if n < MIN_EXPECTED_BYTES:
                    tmp_path.unlink(missing_ok=True)
                    raise OSError(
                        f"downloaded only {n:,} bytes (< {MIN_EXPECTED_BYTES:,}); "
                        "refusing truncated file"
                    )
                tmp_path.replace(dest)
                return
        except (requests.RequestException, OSError) as err:
            last_err = err
            if attempt < retries:
                wait = 2**attempt
                log(f"attempt {attempt} failed ({err}); retrying in {wait}s")
                time.sleep(wait)
    raise RuntimeError(
        f"GWA download failed after {retries} attempts from {url}: {last_err}"
    ) from last_err


def validate(path: Path) -> dict:
    """Open the raster, check it covers Germany, and return stats."""
    with rasterio.open(path) as src:
        b = src.bounds
        lon_min, lat_min, lon_max, lat_max = GERMANY_BBOX
        t = BBOX_TOL_DEG
        if not (
            b.left <= lon_min + t
            and b.bottom <= lat_min + t
            and b.right >= lon_max - t
            and b.top >= lat_max - t
        ):
            raise ValueError(f"raster bounds {tuple(b)} do not cover Germany bbox {GERMANY_BBOX}")
        arr = src.read(1, masked=True)
        if src.nodata is not None:
            arr = np.ma.masked_equal(arr, src.nodata)
        valid = arr.compressed().astype(float)
        if valid.size == 0:
            raise ValueError("raster contains no valid pixels")
        stats = {
            "crs": str(src.crs),
            "size": f"{src.width}x{src.height}",
            "bounds": tuple(round(x, 4) for x in b),
            "valid_pixels": int(valid.size),
            "min_ms": float(valid.min()),
            "mean_ms": float(valid.mean()),
            "max_ms": float(valid.max()),
        }
    if not (0.0 <= stats["min_ms"] and stats["max_ms"] <= 30.0 and 3.0 <= stats["mean_ms"] <= 12.0):
        raise ValueError(f"wind-speed stats implausible for Germany at 100 m: {stats}")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=GWA_URL, help="GWA API URL (default: %(default)s)")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="output GeoTIFF path (default: %(default)s)"
    )
    parser.add_argument(
        "--force", action="store_true", help="re-download even if the file exists and validates"
    )
    args = parser.parse_args()

    if args.out.exists() and not args.force:
        log(f"{args.out} exists; validating cached copy (use --force to re-download)")
        try:
            stats = validate(args.out)
        except (rasterio.errors.RasterioIOError, ValueError) as err:
            log(f"cached file invalid ({err}); re-downloading")
            download(args.url, args.out)
            stats = validate(args.out)
    else:
        download(args.url, args.out)
        stats = validate(args.out)

    log(f"OK {args.out} ({args.out.stat().st_size:,} bytes)")
    log(f"crs={stats['crs']} size={stats['size']} bounds={stats['bounds']}")
    log(
        f"wind speed 100m [m/s]: min={stats['min_ms']:.2f} "
        f"mean={stats['mean_ms']:.2f} max={stats['max_ms']:.2f} "
        f"({stats['valid_pixels']:,} valid pixels)"
    )
    print(
        f"gwa: {args.out} min={stats['min_ms']:.2f} mean={stats['mean_ms']:.2f} "
        f"max={stats['max_ms']:.2f} m/s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
