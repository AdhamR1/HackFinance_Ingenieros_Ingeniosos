"""Data lake layout, logging, HTTP with retries and on-disk cache."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "dc-datalake-hackathon/0.1 (research; contact via project repo)"


def get_logger(log_dir: Path | None = None) -> logging.Logger:
    log = logging.getLogger("dclake")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    h = logging.StreamHandler()
    h.setFormatter(fmt)
    log.addHandler(h)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    return log


def make_session(total_retries: int = 5) -> requests.Session:
    s = requests.Session()
    retry = Retry(total=total_retries, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "POST"), respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = USER_AGENT
    return s


class Lake:
    """root = cache (downloads, intermediates, logs); tables = the final dataset folder."""

    def __init__(self, root: Path, tables: Path | None = None):
        self.root = Path(root)
        self.raw = self.root / "raw"
        self.manual = self.raw / "manual"
        self.processed = self.root / "processed"
        self.staging = self.root / "staging"
        self.tables = Path(tables) if tables else self.root / "tables"
        self.reports = self.root / "reports"
        self.metadata = self.root / "metadata"
        self.logs = self.root / "logs"
        for p in (self.raw, self.processed, self.staging, self.tables, self.metadata, self.logs):
            p.mkdir(parents=True, exist_ok=True)
        self.log = get_logger(self.logs)
        self.http = make_session()
        self.http_once = make_session(total_retries=0)   # for slow services where we handle retries ourselves

    # ---------- cached downloads ----------
    def cached_get(self, url: str, dest: Path, params: dict | None = None, headers: dict | None = None,
                   timeout: int = 120, min_bytes: int = 1, sleep: float = 0.0, method: str = "GET",
                   data: dict | str | None = None, validate=None, retry: bool = True) -> Path | None:
        """Download url to dest once. Returns None on 404 (e.g. ocean DEM tile).

        validate(content: bytes) -> bool rejects error pages served with HTTP 200 (they are not cached).
        """
        dest = Path(dest)
        if dest.exists() and dest.stat().st_size >= min_bytes:
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        http = self.http if retry else self.http_once
        r = http.request(method, url, params=params, headers=headers, timeout=timeout, data=data)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        if validate is not None and not validate(r.content):
            return None
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(r.content)
        tmp.replace(dest)
        if sleep:
            time.sleep(sleep)
        return dest

    def download_file(self, url: str, dest: Path, timeout: int = 600, chunk: int = 1 << 20) -> Path | None:
        """Stream a large file to disk once (no full copy in memory). None on 403/404."""
        dest = Path(dest)
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with self.http.get(url, stream=True, timeout=timeout) as r:
            if r.status_code in (403, 404):
                return None
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for block in r.iter_content(chunk):
                    f.write(block)
        tmp.replace(dest)
        return dest

    def get_json(self, url: str, dest: Path, **kw):
        p = self.cached_get(url, dest, **kw)
        return None if p is None else json.loads(Path(p).read_text(encoding="utf-8"))

    # ---------- staging (outputs of each collector) ----------
    def stage_dir(self, collector: str) -> Path:
        d = self.staging / collector
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_stage(self, collector: str, table: str, df: pd.DataFrame, year: int | None = None):
        if df is None or df.empty:
            return
        d = self.stage_dir(collector)
        if year is not None:
            p = d / table / f"year={year}.parquet"
            p.parent.mkdir(parents=True, exist_ok=True)
        else:
            p = d / f"{table}.parquet"
        df.to_parquet(p, index=False)

    def read_stage(self, collector: str, table: str, year: int | None = None) -> pd.DataFrame | None:
        d = self.staging / collector
        p = d / table / f"year={year}.parquet" if year is not None else d / f"{table}.parquet"
        return pd.read_parquet(p) if p.exists() else None

    def staged_collectors(self) -> list[str]:
        return sorted(p.name for p in self.staging.iterdir() if p.is_dir())

    def write_lineage(self, collector: str, info: dict):
        d = self.stage_dir(collector)
        info = {k: {**v, "retrieved_at": v.get("retrieved_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")}
                for k, v in info.items()}
        old = self.read_lineage(collector)
        old.update(info)
        (d / "_lineage.json").write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")

    def read_lineage(self, collector: str) -> dict:
        p = self.staging / collector / "_lineage.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    # ---------- catalog of downloaded datasets ----------
    def catalog(self, dataset_id: str, source: str, url: str, license: str = "", notes: str = ""):
        p = self.metadata / "catalog.csv"
        row = pd.DataFrame([{
            "dataset_id": dataset_id, "source": source, "url": url, "license": license,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "notes": notes}])
        if p.exists():
            old = pd.read_csv(p)
            old = old[old["dataset_id"] != dataset_id]
            row = pd.concat([old, row], ignore_index=True)
        row.to_csv(p, index=False)

    # ---------- sample of sites ----------
    def sites(self):
        import geopandas as gpd
        p = self.processed / "grid" / "sample_cells.parquet"
        if not p.exists():
            raise FileNotFoundError("No hay muestra de celdas. Ejecuta primero: python -m dclake grid")
        return gpd.read_parquet(p)
