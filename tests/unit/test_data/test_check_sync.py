from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from indicium_ai_agent.config.settings import DataMode
from indicium_ai_agent.data.check_sync import check_and_sync_data


def test_pinned_mode_uses_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "INFLUD26-20-07-2026.csv"
    snapshot.write_text("col1;col2\n1;2\n")
    cache = tmp_path / "cache"
    result = check_and_sync_data(
        data_mode=DataMode.PINNED,
        raw_dir=tmp_path,
        cache_dir=cache,
        resource_url="http://unused",
    )
    assert result["data_check_result"]["action"] == "pinned_snapshot"
    assert str(snapshot) == result["raw_csv_path"]


def test_pinned_mode_missing_snapshot_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No pinned snapshot"):
        check_and_sync_data(
            data_mode=DataMode.PINNED,
            raw_dir=tmp_path,
            cache_dir=tmp_path / "cache",
            resource_url="http://unused",
        )


def test_live_mode_cache_hit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    cache = tmp_path / "cache"
    raw.mkdir()
    cache.mkdir()

    (cache / "csv_metadata.json").write_text(
        json.dumps(
            {
                "filename": "srag_20260720.csv",
                "etag": '"abc123"',
                "last_modified": "Mon, 20 Jul 2026 03:44:43 GMT",
            }
        )
    )
    (raw / "srag_20260720.csv").write_text("col1;col2\n1;2\n")

    class FakeResponse:
        def __init__(self) -> None:
            self.headers = {
                "Last-Modified": "Mon, 20 Jul 2026 03:44:43 GMT",
                "ETag": '"abc123"',
            }

        def raise_for_status(self) -> None:
            pass

    monkeypatch.setattr("httpx.Client.head", lambda _self, _url: FakeResponse())

    result = check_and_sync_data(
        data_mode=DataMode.LIVE,
        raw_dir=raw,
        cache_dir=cache,
        resource_url="http://test",
    )
    assert result["data_check_result"]["action"] == "cached_up_to_date"


def test_live_mode_network_failure_with_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    raw = tmp_path / "raw"
    cache = tmp_path / "cache"
    raw.mkdir()
    cache.mkdir()

    (cache / "csv_metadata.json").write_text(
        json.dumps({"filename": "srag_20260720.csv", "etag": '"abc123"'})
    )
    (raw / "srag_20260720.csv").write_text("col1;col2\n1;2\n")

    def fail(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("Network error", request=httpx.Request("HEAD", "http://test"))

    monkeypatch.setattr("httpx.Client.head", fail)

    result = check_and_sync_data(
        data_mode=DataMode.LIVE,
        raw_dir=raw,
        cache_dir=cache,
        resource_url="http://test",
    )
    assert result["data_check_result"]["action"] == "used_cache_after_error"
    assert "Network error" in result["data_check_result"]["error"]


def test_live_mode_no_cache_no_network_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    raw = tmp_path / "raw"
    cache = tmp_path / "cache"
    raw.mkdir()
    cache.mkdir()

    def fail(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("Network error", request=httpx.Request("HEAD", "http://test"))

    monkeypatch.setattr("httpx.Client.head", fail)

    with pytest.raises(RuntimeError, match="No cached CSV"):
        check_and_sync_data(
            data_mode=DataMode.LIVE,
            raw_dir=raw,
            cache_dir=cache,
            resource_url="http://test",
        )
