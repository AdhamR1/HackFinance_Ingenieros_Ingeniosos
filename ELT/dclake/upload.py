"""Upload the dataset folder to Azure Data Lake Storage Gen2 (same layout: tables + year= partitions).

Configuration in .env:
  AZURE_STORAGE_ACCOUNT     storage account name (with hierarchical namespace = ADLS Gen2)
  AZURE_STORAGE_CONTAINER   container / file system, e.g. dclake
  AZURE_STORAGE_PREFIX      folder inside the container (default: dataset)
  and one way to authenticate:
  AZURE_STORAGE_SAS_TOKEN   SAS token with write permission, or
  AZURE_STORAGE_KEY         account key, or nothing: `az login` / managed identity (DefaultAzureCredential)
"""
from __future__ import annotations

from pathlib import Path


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
        from azure.identity import DefaultAzureCredential
        cred = DefaultAzureCredential()
    return DataLakeServiceClient(account_url=url, credential=cred)


def upload_dataset(lake, cfg) -> int:
    container = cfg.secret("AZURE_STORAGE_CONTAINER")
    if not container:
        raise RuntimeError("Falta AZURE_STORAGE_CONTAINER en .env")
    prefix = (cfg.secret("AZURE_STORAGE_PREFIX") or "dataset").strip("/")
    fs = _client(cfg).get_file_system_client(container)
    if not fs.exists():
        fs.create_file_system()
        lake.log.info("Creado el contenedor %s", container)
    files = sorted(p for p in Path(lake.tables).rglob("*.parquet"))
    total = 0
    for p in files:
        rel = p.relative_to(lake.tables).as_posix()
        with open(p, "rb") as f:
            fs.get_file_client(f"{prefix}/{rel}").upload_data(f, overwrite=True)
        total += p.stat().st_size
        lake.log.info("  subido %s (%.1f MB)", rel, p.stat().st_size / 1e6)
    lake.log.info("Dataset en abfss://%s@%s.dfs.core.windows.net/%s: %d archivos, %.0f MB",
                  container, cfg.secret("AZURE_STORAGE_ACCOUNT"), prefix, len(files), total / 1e6)
    return len(files)
