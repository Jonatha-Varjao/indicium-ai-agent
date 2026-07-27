from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from indicium_ai_agent.config.settings import DataMode
from indicium_ai_agent.data import compute_sha256

logger = logging.getLogger(__name__)


def _load_cache_metadata(cache_dir: Path) -> dict:
    cache_file = cache_dir / "csv_metadata.json"
    if not cache_file.exists():
        return {}
    with open(cache_file) as f:
        return json.load(f)


def _save_cache_metadata(cache_dir: Path, metadata: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "csv_metadata.json"
    with open(cache_file, "w") as f:
        json.dump(metadata, f, indent=2, default=str)


def check_and_sync_data(
    data_mode: DataMode,
    raw_dir: Path,
    cache_dir: Path,
    resource_url: str,
) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()

    if data_mode == DataMode.PINNED:
        snapshot = raw_dir / "INFLUD26-20-07-2026.csv"
        if not snapshot.exists():
            msg = (
                f"No pinned snapshot found at {snapshot}. "
                "Run with DATA_MODE=live to download first."
            )
            raise FileNotFoundError(msg)
        return {
            "raw_csv_path": str(snapshot),
            "data_check_result": {
                "action": "pinned_snapshot",
                "checked_at": checked_at,
            },
        }

    raw_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        with httpx.Client(timeout=10) as client:
            head = client.head(resource_url)
            head.raise_for_status()
            remote_last_modified = head.headers.get("Last-Modified", "")
            remote_etag = head.headers.get("ETag", "")
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("Freshness check failed: %s", exc)
        return _fallback_to_cache(raw_dir, cache_dir, checked_at, str(exc))

    cached = _load_cache_metadata(cache_dir)
    cache_hit = (
        cached.get("etag") == remote_etag
        or cached.get("last_modified") == remote_last_modified
    )

    if cache_hit and cached.get("filename"):
        logger.info("CSV is up to date (etag match). Using cached: %s", cached["filename"])
        return {
            "raw_csv_path": str(raw_dir / cached["filename"]),
            "data_check_result": {
                "action": "cached_up_to_date",
                "remote_last_modified": remote_last_modified,
                "remote_etag": remote_etag,
                "cached_last_modified": cached.get("last_modified", ""),
                "checked_at": checked_at,
            },
        }

    logger.info("Fresh CSV available. Downloading %s ...", resource_url)
    try:
        df = pd.read_csv(resource_url, sep=";", encoding="latin-1", low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(resource_url, sep=";", encoding="utf-8", low_memory=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CSV download failed: %s", exc)
        return _fallback_to_cache(raw_dir, cache_dir, checked_at, str(exc))

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"srag_{timestamp}.csv"
    dest = raw_dir / filename
    df.to_csv(dest, sep=";", index=False)
    sha = compute_sha256(dest)

    meta = {
        "filename": filename,
        "etag": remote_etag,
        "last_modified": remote_last_modified,
        "checked_at": checked_at,
        "sha256": sha,
        "rows": len(df),
    }
    _save_cache_metadata(cache_dir, meta)

    return {
        "raw_csv_path": str(dest),
        "data_check_result": {
            "action": "downloaded",
            "remote_last_modified": remote_last_modified,
            "remote_etag": remote_etag,
            "checked_at": checked_at,
        },
    }


def _fallback_to_cache(
    raw_dir: Path,
    cache_dir: Path,
    checked_at: str,
    error: str,
) -> dict[str, Any]:
    cached = _load_cache_metadata(cache_dir)
    if cached.get("filename"):
        fallback = raw_dir / cached["filename"]
        if fallback.exists():
            logger.info("Falling back to cached CSV: %s", fallback)
            return {
                "raw_csv_path": str(fallback),
                "data_check_result": {
                    "action": "used_cache_after_error",
                    "error": error,
                    "checked_at": checked_at,
                },
            }

    msg = "No cached CSV available and freshness check / download failed."
    raise RuntimeError(msg)
