"""Resumable partial fetch of the MaStR Gesamtdatenexport (wind + catalogs).

The BNetzA download server throttles to ~50–120 kB/s per IP and drops
connections frequently; open-mastr's serial member download restarts whole
members on every drop and starves. This module reads the remote ZIP's central
directory via HTTP range requests, selects only the members needed for the
onshore-wind units table (EinheitenWind*.xml + Katalogwerte/-kategorien), and
downloads each member's compressed bytes in small resumable chunks with retry.
Total transfer ≈ 20–40 MB instead of 3 GB.

Raw member bytes are cached under data/raw/mastr/members/ — re-runs resume.
License: DL-DE/BY-2.0 (Marktstammdatenregister, Bundesnetzagentur).
"""

from __future__ import annotations

import io
import logging
import re
import struct
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests

BASE = "https://download.marktstammdatenregister.de"
CHUNK = 1_048_576  # 1 MiB range chunks — small enough to survive flaky drops
WORKERS = 6
RETRIES = 8
TIMEOUT = 90

log = logging.getLogger("mastr_zip_fetch")


@dataclass(frozen=True)
class Member:
    name: str
    method: int  # 0 = stored, 8 = deflate
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) rheingold-pipeline/0.1 "
        "(non-commercial research; resumable range fetch)"
    )
    return s


def _get_range(s: requests.Session, url: str, start: int, end: int) -> bytes:
    """Inclusive byte range with retry/backoff; returns exactly the requested bytes."""
    want = end - start + 1
    for attempt in range(RETRIES):
        try:
            r = s.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=TIMEOUT)
            if r.status_code in (200, 206) and len(r.content) >= want:
                return r.content[:want]
            if r.status_code == 206 and 0 < len(r.content) < want:
                # partial partial — accept and let caller-side chunking resume
                return r.content
            raise OSError(f"HTTP {r.status_code}, {len(r.content)} bytes for {want}")
        except (requests.RequestException, OSError) as exc:
            wait = min(60.0, 2.0**attempt)
            log.warning(
                "range %d-%d attempt %d failed (%s) — retry in %.0fs",
                start,
                end,
                attempt + 1,
                exc,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"range {start}-{end} failed after {RETRIES} attempts")


def find_export_url(s: requests.Session, days_back: int = 4) -> tuple[str, str, int]:
    """Probe today backwards for the daily export. Returns (url, yyyymmdd, size)."""
    import datetime as dt

    today = dt.date.today()
    versions = ["26.1", "26.2", "25.2", "27.1"]
    for delta in range(days_back + 1):
        d = today - dt.timedelta(days=delta)
        for v in versions:
            url = f"{BASE}/Gesamtdatenexport_{d:%Y%m%d}_{v}.zip"
            try:
                r = s.head(url, timeout=30)
            except requests.RequestException:
                continue
            if r.status_code == 200 and "Content-Length" in r.headers:
                return url, f"{d:%Y%m%d}", int(r.headers["Content-Length"])
    raise RuntimeError("no Gesamtdatenexport found in the last days — check BNetzA download page")


def read_central_directory(s: requests.Session, url: str, total_size: int) -> list[Member]:
    """Parse EOCD(64) from the file tail, then the central directory, via ranges."""
    tail_len = min(total_size, 4_194_304)
    tail = _get_range(s, url, total_size - tail_len, total_size - 1)

    eocd_pos = tail.rfind(b"PK\x05\x06")
    if eocd_pos < 0:
        raise RuntimeError("EOCD signature not found in file tail")
    cd_size, cd_offset = struct.unpack_from("<II", tail, eocd_pos + 12)
    if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        loc = tail.rfind(b"PK\x06\x07")  # zip64 EOCD locator
        if loc < 0:
            raise RuntimeError("zip64 locator not found")
        (eocd64_offset,) = struct.unpack_from("<Q", tail, loc + 8)
        rel = eocd64_offset - (total_size - tail_len)
        if rel < 0:
            eocd64 = _get_range(s, url, eocd64_offset, eocd64_offset + 55)
            rel, tail64 = 0, eocd64
        else:
            tail64 = tail
        if tail64[rel : rel + 4] != b"PK\x06\x06":
            raise RuntimeError("zip64 EOCD signature mismatch")
        cd_size, cd_offset = struct.unpack_from("<QQ", tail64, rel + 40)

    cd = (
        tail[cd_offset - (total_size - tail_len) : cd_offset - (total_size - tail_len) + cd_size]
        if cd_offset >= total_size - tail_len
        else _get_range(s, url, cd_offset, cd_offset + cd_size - 1)
    )

    members: list[Member] = []
    pos = 0
    while pos + 46 <= len(cd):
        if cd[pos : pos + 4] != b"PK\x01\x02":
            break
        method = struct.unpack_from("<H", cd, pos + 10)[0]
        csize = struct.unpack_from("<I", cd, pos + 20)[0]
        usize = struct.unpack_from("<I", cd, pos + 24)[0]
        nlen = struct.unpack_from("<H", cd, pos + 28)[0]
        elen = struct.unpack_from("<H", cd, pos + 30)[0]
        clen = struct.unpack_from("<H", cd, pos + 32)[0]
        lho = struct.unpack_from("<I", cd, pos + 42)[0]
        name = cd[pos + 46 : pos + 46 + nlen].decode("cp437")
        extra = cd[pos + 46 + nlen : pos + 46 + nlen + elen]
        # zip64 extra field overrides
        if 0xFFFFFFFF in (csize, usize, lho):
            epos = 0
            while epos + 4 <= len(extra):
                eid, esz = struct.unpack_from("<HH", extra, epos)
                if eid == 0x0001:
                    vals = []
                    vpos = epos + 4
                    for sentinel in (usize, csize, lho):
                        if sentinel == 0xFFFFFFFF:
                            vals.append(struct.unpack_from("<Q", extra, vpos)[0])
                            vpos += 8
                        else:
                            vals.append(sentinel)
                    usize, csize, lho = vals
                    break
                epos += 4 + esz
        members.append(Member(name, method, csize, usize, lho))
        pos += 46 + nlen + elen + clen
    if not members:
        raise RuntimeError("central directory parsed to zero members")
    return members


def _data_offset(s: requests.Session, url: str, m: Member) -> int:
    """Resolve the member's data start (local header is variable-length)."""
    hdr = _get_range(s, url, m.local_header_offset, m.local_header_offset + 29)
    if hdr[:4] != b"PK\x03\x04":
        raise RuntimeError(f"bad local header for {m.name}")
    nlen, elen = struct.unpack_from("<HH", hdr, 26)
    return m.local_header_offset + 30 + nlen + elen


def fetch_member(s: requests.Session, url: str, m: Member, cache_dir: Path) -> Path:
    """Download the member's raw compressed bytes, chunked + resumable."""
    out = cache_dir / (re.sub(r"[^A-Za-z0-9._-]", "_", m.name) + ".raw")
    if out.exists() and out.stat().st_size == m.compressed_size:
        return out
    part = out.with_suffix(".raw.part")
    have = part.stat().st_size if part.exists() else 0
    start = _data_offset(s, url, m) + have
    end_abs = _data_offset(s, url, m) + m.compressed_size - 1
    with open(part, "ab") as fh:
        while start <= end_abs:
            chunk_end = min(start + CHUNK - 1, end_abs)
            data = _get_range(s, url, start, chunk_end)
            fh.write(data)
            fh.flush()
            start += len(data)
            done = start - (_data_offset(s, url, m))
            log.info("%s: %.1f/%.1f MB", m.name, done / 1e6, m.compressed_size / 1e6)
    if part.stat().st_size != m.compressed_size:
        raise RuntimeError(f"{m.name}: size mismatch after download")
    part.rename(out)
    return out


def decompress_member(m: Member, raw_path: Path) -> bytes:
    raw = raw_path.read_bytes()
    if m.method == 0:
        return raw
    if m.method == 8:
        return zlib.decompress(raw, wbits=-15)
    raise RuntimeError(f"{m.name}: unsupported compression method {m.method}")


def fetch_wind_members(cache_root: Path) -> tuple[dict[str, bytes], str]:
    """Download + decompress EinheitenWind* and catalog members. Returns ({name: xml_bytes}, snapshot)."""
    s = _session()
    url, snapshot, total = find_export_url(s)
    log.info("export: %s (%.2f GB)", url, total / 1e9)
    cache = cache_root / "members"
    cache.mkdir(parents=True, exist_ok=True)

    members = read_central_directory(s, url, total)
    wanted = [
        m
        for m in members
        if re.match(r"(EinheitenWind|Katalogwerte|Katalogkategorien)", m.name, re.IGNORECASE)
    ]
    if not wanted:
        names = ", ".join(m.name for m in members[:40])
        raise RuntimeError(f"no wind/catalog members found; first members: {names}")
    log.info(
        "fetching %d members, %.1f MB compressed total",
        len(wanted),
        sum(m.compressed_size for m in wanted) / 1e6,
    )

    results: dict[str, bytes] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(fetch_member, _session(), url, m, cache): m for m in wanted}
        for fut in as_completed(futs):
            m = futs[fut]
            raw_path = fut.result()
            results[m.name] = decompress_member(m, raw_path)
            log.info("done: %s (%.1f MB xml)", m.name, len(results[m.name]) / 1e6)
    return results, f"{snapshot[:4]}-{snapshot[4:6]}-{snapshot[6:]}"


def parse_katalog(xml_by_name: dict[str, bytes]) -> dict[str, str]:
    """Katalogwerte Id → Wert (ids are globally unique across categories)."""
    import xml.etree.ElementTree as ET

    mapping: dict[str, str] = {}
    for name, blob in xml_by_name.items():
        if not re.match(r"Katalogwerte", name, re.IGNORECASE):
            continue
        for _, elem in ET.iterparse(io.BytesIO(blob)):
            if elem.tag.endswith("Katalogwert"):
                kid = elem.findtext("Id")
                wert = elem.findtext("Wert")
                if kid is not None and wert is not None:
                    mapping[kid] = wert
                elem.clear()
    if not mapping:
        raise RuntimeError("Katalogwerte parsed to empty mapping")
    return mapping


def parse_wind_units(xml_by_name: dict[str, bytes]) -> list[dict]:
    """All EinheitenWind records as raw string dicts (field name → text)."""
    import xml.etree.ElementTree as ET

    rows: list[dict] = []
    for name in sorted(xml_by_name):
        if not re.match(r"EinheitenWind", name, re.IGNORECASE):
            continue
        for _, elem in ET.iterparse(io.BytesIO(xml_by_name[name])):
            if elem.tag == "EinheitWind":
                rows.append({child.tag: child.text for child in elem})
                elem.clear()
    if not rows:
        raise RuntimeError("EinheitenWind parsed to zero records")
    return rows


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
    xml_by_name, snap = fetch_wind_members(Path("data/raw/mastr"))
    print("snapshot", snap, "| members:", {k: len(v) // 1024 for k, v in xml_by_name.items()})
    rows = parse_wind_units(xml_by_name)
    kat = parse_katalog(xml_by_name)
    print("units:", len(rows), "| katalog entries:", len(kat))
    print("sample field names:", sorted(rows[0].keys())[:40])
