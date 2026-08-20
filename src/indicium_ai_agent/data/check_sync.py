"""Check and sync DATASUS SRAG data with freshness validation and caching."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, cast

import httpx
import pandas as pd
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from indicium_ai_agent.config.settings import PINNED_SNAPSHOT_FILENAME, DataMode
from indicium_ai_agent.data import compute_sha256

logger = logging.getLogger(__name__)

HTTP_TIMEOUT: int = 10


class CacheMetadata(TypedDict, total=False):
    """Metadata stored in ``csv_metadata.json``."""

    filename: str
    etag: str
    last_modified: str
    checked_at: str
    sha256: str
    rows: int


class DataCheckResult(TypedDict, total=False):
    """Result of the freshness / sync check."""

    action: str
    checked_at: str
    remote_last_modified: str
    remote_etag: str
    cached_last_modified: str
    error: str


class SyncResult(TypedDict):
    """Return value of :func:`check_and_sync_data`."""

    raw_csv_path: str
    data_check_result: DataCheckResult


def _load_cache_metadata(cache_dir: Path) -> CacheMetadata:
    """Load cached metadata from ``csv_metadata.json``.

    Args:
        cache_dir: Directory containing the metadata file.

    Returns:
        Cached metadata dict, or empty dict if file missing.
    """
    cache_file = cache_dir / "csv_metadata.json"
    if not cache_file.exists():
        return {}
    with open(cache_file) as f:
        data: Any = json.load(f)
        return cast(CacheMetadata, data)


def _save_cache_metadata(cache_dir: Path, metadata: CacheMetadata) -> None:
    """Persist cache metadata to ``csv_metadata.json``.

    Args:
        cache_dir: Directory to store the metadata file.
        metadata: Metadata to persist.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "csv_metadata.json"
    with open(cache_file, "w") as f:
        json.dump(metadata, f, indent=2, default=str)


def _resolve_pinned_path(raw_dir: Path, checked_at: str) -> SyncResult:
    """Resolve pinned snapshot path.

    Args:
        raw_dir: Directory containing the pinned CSV.
        checked_at: ISO timestamp of the check.

    Returns:
        Sync result pointing to the pinned snapshot.

    Raises:
        FileNotFoundError: If the pinned snapshot does not exist.
    """
    snapshot = raw_dir / PINNED_SNAPSHOT_FILENAME
    if not snapshot.exists():
        msg = f"No pinned snapshot found at {snapshot}. Run with DATA_MODE=live to download first."
        raise FileNotFoundError(msg)
    return {
        "raw_csv_path": str(snapshot),
        "data_check_result": {
            "action": "pinned_snapshot",
            "checked_at": checked_at,
        },
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _fetch_head(resource_url: str) -> tuple[str, str]:
    """Fetch ``Last-Modified`` and ``ETag`` via HEAD with retry.

    Args:
        resource_url: Remote URL to check.

    Returns:
        Tuple of ``(last_modified, etag)`` header values.

    Raises:
        httpx.HTTPError: If the request fails after retries.
    """
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        head = client.head(resource_url)
        head.raise_for_status()
        remote_last_modified = head.headers.get("Last-Modified", "")
        remote_etag = head.headers.get("ETag", "")
        return remote_last_modified, remote_etag


def _check_freshness(resource_url: str) -> tuple[str, str]:
    """Check freshness via HEAD request with exponential backoff.

    Args:
        resource_url: Remote URL to check.

    Returns:
        Tuple of ``(last_modified, etag)``.
    """
    return _fetch_head(resource_url)


def _is_cache_hit(
    cached: CacheMetadata,
    remote_last_modified: str,
    remote_etag: str,
) -> bool:
    """Determine if cached metadata matches remote headers."""
    etag_match = cached.get("etag") == remote_etag and remote_etag != ""
    modified_match = (
        cached.get("last_modified") == remote_last_modified and remote_last_modified != ""
    )
    return etag_match or modified_match


def _stream_to_file(resource_url: str, dest: Path) -> None:
    """Stream-download ``resource_url`` to ``dest`` via httpx.

    Args:
        resource_url: Remote URL.
        dest: Local file path to write.

    Raises:
        httpx.HTTPError: On HTTP failure.
        OSError: On file write failure.
    """
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        with client.stream("GET", resource_url, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)


def _read_csv_with_fallback(dest: Path) -> pd.DataFrame:
    """Read CSV from ``dest`` with encoding fallback.

    Tries ``latin-1`` first (DATASUS default), falls back to ``utf-8`` on
    ``UnicodeDecodeError``.

    Args:
        dest: Local CSV path.

    Returns:
        Parsed DataFrame.
    """
    try:
        return pd.read_csv(dest, sep=";", encoding="latin-1", low_memory=False)
    except UnicodeDecodeError:
        return pd.read_csv(dest, sep=";", encoding="utf-8", low_memory=False)


def _safe_unlink(path: Path) -> None:
    """Remove file if it exists, ignoring missing errors."""
    if path.exists():
        path.unlink(missing_ok=True)


def _download_and_cache(
    resource_url: str,
    raw_dir: Path,
    cache_dir: Path,
    remote_last_modified: str,
    remote_etag: str,
    checked_at: str,
) -> SyncResult:
    """Stream-download CSV via httpx, parse locally, and cache.

    Uses streaming download to avoid double fetching (previously
    ``pd.read_csv(resource_url)`` downloaded twice — once for HEAD and again
    for the body). Handles encoding fallback and narrow exception types;
    ``BaseException`` subclasses like ``KeyboardInterrupt`` are not caught.

    Args:
        resource_url: Remote CSV URL.
        raw_dir: Directory to store the downloaded CSV.
        cache_dir: Directory to store metadata.
        remote_last_modified: Remote ``Last-Modified`` header.
        remote_etag: Remote ``ETag`` header.
        checked_at: ISO timestamp of the check.

    Returns:
        Sync result indicating ``downloaded`` or fallback on error.
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"srag_{timestamp}.csv"
    dest = raw_dir / filename
    raw_dir.mkdir(parents=True, exist_ok=True)

    try:
        _stream_to_file(resource_url, dest)
    except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
        logger.warning("CSV download failed: %s", exc)
        _safe_unlink(dest)
        return _fallback_to_cache(raw_dir, cache_dir, checked_at, str(exc))
    except Exception as exc:
        logger.warning("Unexpected download error: %s", exc)
        _safe_unlink(dest)
        return _fallback_to_cache(raw_dir, cache_dir, checked_at, str(exc))

    try:
        df = _read_csv_with_fallback(dest)
    except (pd.errors.ParserError, OSError, ValueError) as exc:
        logger.warning("CSV parsing failed: %s", exc)
        _safe_unlink(dest)
        return _fallback_to_cache(raw_dir, cache_dir, checked_at, str(exc))
    except Exception as exc:
        logger.warning("Unexpected parsing error: %s", exc)
        _safe_unlink(dest)
        return _fallback_to_cache(raw_dir, cache_dir, checked_at, str(exc))

    # BaseException (KeyboardInterrupt, SystemExit) intentionally not caught

    df.to_csv(dest, sep=";", index=False)
    sha = compute_sha256(dest)

    meta: CacheMetadata = {
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
) -> SyncResult:
    """Fallback to cached CSV if available.

    Args:
        raw_dir: Directory containing cached CSVs.
        cache_dir: Directory containing metadata.
        checked_at: ISO timestamp.
        error: Error message that triggered fallback.

    Returns:
        Sync result pointing to cached file.

    Raises:
        RuntimeError: If no cached file is available.
    """
    cached = _load_cache_metadata(cache_dir)
    if cached.get("filename"):
        fallback = raw_dir / str(cached["filename"])
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


def check_and_sync_data(
    data_mode: DataMode,
    raw_dir: Path,
    cache_dir: Path,
    resource_url: str,
) -> SyncResult:
    """Check data freshness and sync CSV.

    Orchestrates pinned snapshot resolution, freshness check with retry,
    cache-hit shortcut, and streaming download.

    Args:
        data_mode: ``PINNED`` returns local snapshot, ``LIVE`` checks remote.
        raw_dir: Directory for raw CSVs.
        cache_dir: Directory for cache metadata.
        resource_url: Remote CSV URL for live mode.

    Returns:
        Dict with ``raw_csv_path`` and ``data_check_result``.
    """
    checked_at = datetime.now(UTC).isoformat()

    if data_mode == DataMode.PINNED:
        return _resolve_pinned_path(raw_dir, checked_at)

    raw_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        remote_last_modified, remote_etag = _check_freshness(resource_url)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("Freshness check failed: %s", exc)
        return _fallback_to_cache(raw_dir, cache_dir, checked_at, str(exc))
    except Exception as exc:
        logger.warning("Unexpected freshness error: %s", exc)
        return _fallback_to_cache(raw_dir, cache_dir, checked_at, str(exc))

    cached = _load_cache_metadata(cache_dir)

    if _is_cache_hit(cached, remote_last_modified, remote_etag) and cached.get("filename"):
        logger.info("CSV is up to date (etag match). Using cached: %s", cached["filename"])
        return {
            "raw_csv_path": str(raw_dir / str(cached["filename"])),
            "data_check_result": {
                "action": "cached_up_to_date",
                "remote_last_modified": remote_last_modified,
                "remote_etag": remote_etag,
                "cached_last_modified": str(cached.get("last_modified", "")),
                "checked_at": checked_at,
            },
        }

    logger.info("Fresh CSV available. Downloading %s ...", resource_url)
    return _download_and_cache(
        resource_url,
        raw_dir,
        cache_dir,
        remote_last_modified,
        remote_etag,
        checked_at,
    )
