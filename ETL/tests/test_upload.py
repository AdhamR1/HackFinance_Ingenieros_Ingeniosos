"""Offline tests for dclake.upload with a fake Azure Data Lake client (no network, no azure)."""

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


def test_extra_dirs_go_next_to_the_dataset(tmp_path, monkeypatch):
    tables, extra = tmp_path / "ETL" / "dataset", tmp_path / "Modelo" / "processed"
    for p, data in {
        tables / "sites.parquet": b"aa",
        extra / "scores.parquet": b"bbb",
        extra / "priors.csv": b"c",
        extra / ".hidden": b"d",
    }.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    class Cfg(dict):
        root = tmp_path / "ETL"
        secret = staticmethod(SECRETS.get)

    cfg = Cfg(azure={"extra_dirs": {"processed": "../Modelo/processed", "gone": "../nope"}})
    lake = SimpleNamespace(tables=tables, log=logging.getLogger("dclake.test"))
    fs = FakeFS(remote={"processed/priors.csv": 1})  # already there with the same size
    monkeypatch.setattr(
        upload, "_client", lambda cfg: SimpleNamespace(get_file_system_client=lambda c: fs)
    )
    assert upload.upload_dataset(lake, cfg) == 3
    assert sorted(fs.uploads) == ["dataset/sites.parquet", "processed/scores.parquet"]


def test_set_env_values_keeps_other_lines(tmp_path):
    from dclake.azure_setup import set_env_values

    env = tmp_path / ".env"
    env.write_text("# comment\nOTHER_KEY=keep\nAZURE_STORAGE_ACCOUNT=\n", encoding="utf-8")
    set_env_values(
        env, {"AZURE_STORAGE_ACCOUNT": "stdclakeabc123", "AZURE_STORAGE_SAS_TOKEN": "s"}
    )
    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines[:3] == ["# comment", "OTHER_KEY=keep", "AZURE_STORAGE_ACCOUNT=stdclakeabc123"]
    assert lines[-1] == "AZURE_STORAGE_SAS_TOKEN=s" and len(lines) == 6
    set_env_values(env, {"AZURE_STORAGE_SAS_TOKEN": "t"})  # renewing replaces, never duplicates
    assert env.read_text(encoding="utf-8").count("AZURE_STORAGE_SAS_TOKEN=") == 1


def test_dry_run_without_azure(env):
    fs = FakeFS(remote={"dataset/sites.parquet": 10})
    fs.exists = MagicMock(side_effect=Exception("DefaultAzureCredential failed\n(long details)"))
    assert env(fs, dry_run=True) == 3  # lists every local file, nothing compared or uploaded
    assert fs.uploads == []
    with pytest.raises(Exception, match="DefaultAzureCredential"):
        env(fs)  # a real upload still fails loudly
