"""Upload the dataset folder to Azure Data Lake Storage Gen2 (same layout: tables + year=).

Configuration in .env:
  AZURE_STORAGE_ACCOUNT     storage account name (with hierarchical namespace = ADLS Gen2)
  AZURE_STORAGE_CONTAINER   container / file system, e.g. dclake
  AZURE_STORAGE_PREFIX      folder inside the container (default: dataset)
  and one way to authenticate:
  AZURE_STORAGE_SAS_TOKEN   SAS token with write permission, or
  AZURE_STORAGE_KEY         account key, or
  nothing                   `az login` / managed identity (DefaultAzureCredential)

Uploads run in parallel, are retried with exponential backoff and are incremental: a file that
already exists in Azure with the same size is skipped unless force=True. A SAS token without
permission to check/create the container or to list paths is tolerated (everything is then
uploaded).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RETRIES = 4  # attempts per file
BACKOFF_S = 1.0  # wait before retry n: BACKOFF_S * 2**(n-1) -> 1, 2, 4 s
DEFAULT_WORKERS = 4
_NO_RETRY = {400, 401, 403, 404, 409, 412}  # client errors: retrying will not help


def _client(cfg):
    from azure.storage.filedatalake import DataLakeServiceClient

    account = cfg.secret("AZURE_STORAGE_ACCOUNT")
    if not account:
        raise RuntimeError("Falta AZURE_STORAGE_ACCOUNT en .env")
    url = f"https://{account}.dfs.core.windows.net"
    sas, key = cfg.secret("AZURE_STORAGE_SAS_TOKEN"), cfg.secret("AZURE_STORAGE_KEY")
    if sas:
        cred = sas.lstrip("?")
    elif key:
        cred = key
    else:
        import logging

        from azure.identity import DefaultAzureCredential

        # its per-credential warnings are repeated in the exception it raises: print them once
        logging.getLogger("azure.identity").setLevel(logging.ERROR)
        cred = DefaultAzureCredential()
    return DataLakeServiceClient(account_url=url, credential=cred)


@dataclass
class UploadSummary:
    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    bytes_uploaded: int = 0
    bytes_skipped: int = 0


def _status(e: BaseException) -> int | None:
    """HTTP status of an azure.core HttpResponseError (duck-typed: azure not needed at import)."""
    return getattr(e, "status_code", None)


def _ensure_container(fs, container: str, log, dry_run: bool) -> None:
    """Create the container if missing; a SAS scoped to the container may not allow checking it."""
    try:
        if fs.exists():
            return
    except Exception as e:
        if _status(e) in (401, 403):
            log.info("Sin permiso para comprobar el contenedor %s; se asume que existe", container)
            return
        raise
    if dry_run:
        log.info("[dry-run] se crearía el contenedor %s", container)
        return
    try:
        fs.create_file_system()
        log.info("Creado el contenedor %s", container)
    except Exception as e:
        if _status(e) in (401, 403, 409):  # no permission, or created meanwhile
            log.warning(
                "No se pudo crear el contenedor %s (%s); se intenta subir igualmente", container, e
            )
            return
        raise


def _remote_sizes(fs, prefix: str, log) -> dict[str, int]:
    """Size of every file under prefix in Azure, in one listing. Empty if it cannot be listed."""
    try:
        return {
            p.name: int(p.content_length or 0)
            for p in fs.get_paths(path=prefix, recursive=True)
            if not p.is_directory
        }
    except Exception as e:
        if _status(e) == 404:  # prefix not created yet
            return {}
        log.warning("No se pueden listar los archivos en Azure (%s); se suben todos", e)
        return {}


def _upload_one(fs, local: Path, remote: str) -> None:
    for attempt in range(1, RETRIES + 1):
        try:
            with open(local, "rb") as f:
                fs.get_file_client(remote).upload_data(f, overwrite=True)
            return
        except Exception as e:
            if attempt == RETRIES or _status(e) in _NO_RETRY:
                raise
            time.sleep(BACKOFF_S * 2 ** (attempt - 1))


def upload_dataset(
    lake, cfg, *, force: bool = False, dry_run: bool = False, workers: int = DEFAULT_WORKERS
) -> int:
    """Upload lake.tables/**/*.parquet to Azure. Returns the number of files that are in Azure
    (uploaded + skipped; in dry-run, the ones that would be). Raises RuntimeError at the end if
    any failed."""
    log = lake.log
    container = cfg.secret("AZURE_STORAGE_CONTAINER")
    account = cfg.secret("AZURE_STORAGE_ACCOUNT")
    prefix = (cfg.secret("AZURE_STORAGE_PREFIX") or "dataset").strip("/")
    try:
        if not container:
            raise RuntimeError("Falta AZURE_STORAGE_CONTAINER en .env")
        fs = _client(cfg).get_file_system_client(container)
        _ensure_container(fs, container, log, dry_run)
    except Exception as e:
        if not dry_run:
            raise
        # A dry run must also work without Azure: list the local files, compare with nothing
        log.warning(
            "[dry-run] Sin conexión con Azure (%s): se listan todos los archivos locales "
            "sin comparar con lo ya subido",
            str(e).splitlines()[0],
        )
        fs = None

    tables = Path(lake.tables)
    files = sorted(tables.rglob("*.parquet"))
    remote = {} if force or fs is None else _remote_sizes(fs, prefix, log)
    s = UploadSummary()
    todo: list[tuple[Path, str, int]] = []
    for p in files:
        name, size = f"{prefix}/{p.relative_to(tables).as_posix()}", p.stat().st_size
        if remote.get(name) == size:
            s.skipped.append(name)
            s.bytes_skipped += size
        else:
            todo.append((p, name, size))

    t0 = time.time()
    if dry_run:
        for _, name, size in todo:
            log.info("  [dry-run] se subiría %s (%.1f MB)", name, size / 1e6)
            s.uploaded.append(name)
            s.bytes_uploaded += size
    elif todo:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futures: dict[Any, tuple[str, int]] = {
                ex.submit(_upload_one, fs, p, name): (name, size) for p, name, size in todo
            }
            for fut in as_completed(futures):
                name, size = futures[fut]
                try:
                    fut.result()
                except Exception as e:  # one failing file must not stop the rest
                    s.failed[name] = f"{type(e).__name__}: {e}"
                    log.error("  FALLO %s: %s", name, s.failed[name])
                else:
                    s.uploaded.append(name)
                    s.bytes_uploaded += size
                    log.info("  subido %s (%.1f MB)", name, size / 1e6)

    verb = "se subirían" if dry_run else "subidos"
    log.info(
        "Azure abfss://%s@%s.dfs.core.windows.net/%s: %s %d (%.1f MB), "
        "omitidos %d sin cambios (%.1f MB), fallidos %d, %.0f s",
        container,
        account,
        prefix,
        verb,
        len(s.uploaded),
        s.bytes_uploaded / 1e6,
        len(s.skipped),
        s.bytes_skipped / 1e6,
        len(s.failed),
        time.time() - t0,
    )
    if s.failed:
        raise RuntimeError(
            f"Fallaron {len(s.failed)} de {len(files)} archivos: {sorted(s.failed)}"
        )
    return len(s.uploaded) + len(s.skipped)
