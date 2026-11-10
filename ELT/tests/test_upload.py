"""Offline tests for dclake.upload with a fake Azure Data Lake client (no network, azure not
required)."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dclake import upload

SECRETS = {
    "AZURE_STORAGE_ACCOUNT": "acct",
    "AZURE_STORAGE_CONTAINER": "dclake",
    "AZURE_STORAGE_PREFIX": "dataset",
}


class HttpError(Exception):
    """Stand-in for azure.core.exceptions.HttpResponseError (only status_code matters)."""

    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class FakeFS:
    """Fake DataLakeFileSystemClient: records uploads; errors per remote path can be scripted."""

    def __init__(
        self,
        remote: dict[str, int] | None = None,
        errors: dict[str, list[Exception]] | None = None,
    ):
        self.remote = remote or {}
        self.errors = errors or {}
        self.uploads: list[str] = []
        self.exists = MagicMock(side_effect=HttpError(403))  # SAS without container permissions
        self.create_file_system = MagicMock()

    def get_paths(self, path: str, recursive: bool):
        return [
            SimpleNamespace(name=n, content_length=s, is_directory=False)
            for n, s in self.remote.items()
        ]

    def get_file_client(self, name: str):
        def upload_data(f, overwrite):
            assert overwrite and f.read()
            pending = self.errors.get(name)
            if pending:
                raise pending.pop(0)
            self.uploads.append(name)

        return SimpleNamespace(upload_data=upload_data)


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    tables = tmp_path / "tables"
    for rel, size in {
        "sites.parquet": 10,
        "sites_daily/year=2025/part.parquet": 20,
        "hazards.parquet": 30,
    }.items():
        (tables / rel).parent.mkdir(parents=True, exist_ok=True)
        (tables / rel).write_bytes(b"x" * size)
    lake = SimpleNamespace(tables=tables, log=logging.getLogger("dclake.test"))
    cfg = SimpleNamespace(secret=SECRETS.get)
    monkeypatch.setattr(upload.time, "sleep", lambda s: None)

    def run(fs: FakeFS, **kw):
        monkeypatch.setattr(
            upload, "_client", lambda cfg: SimpleNamespace(get_file_system_client=lambda c: fs)
        )
        return upload.upload_dataset(lake, cfg, **kw)

    return run


def test_incremental_skips_same_size_and_retries(env):
    fs = FakeFS(
        remote={"dataset/sites.parquet": 10, "dataset/hazards.parquet": 999},
        errors={"dataset/hazards.parquet": [HttpError(503), HttpError(503)]},
    )
    assert env(fs, workers=2) == 3
    assert sorted(fs.uploads) == [
        "dataset/hazards.parquet",
        "dataset/sites_daily/year=2025/part.parquet",
    ]
    fs.create_file_system.assert_not_called()


def test_force_dry_run_and_failures(env):
    fs = FakeFS(remote={"dataset/sites.parquet": 10})
    assert env(fs, force=True, dry_run=True) == 3
    assert fs.uploads == []

    fs = FakeFS(errors={"dataset/sites.parquet": [HttpError(403)]})  # 403 is not retried
    with pytest.raises(RuntimeError, match=r"sites\.parquet"):
        env(fs, force=True)
    assert len(fs.uploads) == 2  # the other files were still uploaded
