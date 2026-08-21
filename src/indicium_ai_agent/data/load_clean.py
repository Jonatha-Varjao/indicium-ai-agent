"""Load and clean SRAG CSV data."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, TypedDict

import duckdb
import pandas as pd

from indicium_ai_agent.data import compute_sha256
from indicium_ai_agent.data.data_quality import (
    detect_encoding,
    select_columns,
    verify_and_log_pii,
)

logger = logging.getLogger(__name__)

# Regex to extract DD-MM-YYYY before .csv (e.g., INFLUD26-20-07-2026.csv -> 2026-07-20)
_EXTRACTION_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})\.csv$")


class LoadResult(TypedDict):
    """Result of :func:`load_and_clean`."""

    con: duckdb.DuckDBPyConnection
    exclusion_log: dict[str, Any]
    source_csv_hash: str
    source_extraction_date: str


def load_and_clean(csv_path: str | Path) -> LoadResult:
    """Load SRAG CSV, strip PII, select columns, and register DuckDB.

    Args:
        csv_path: Path to the source CSV file.

    Returns:
        Typed dict with DuckDB connection, exclusion log, file hash and
        extraction date.

    Raises:
        FileNotFoundError: If the CSV does not exist.

    Note:
        Caller is responsible for closing the returned DuckDB connection
        via ``result["con"].close()`` when done.
    """
    exclusion_log: dict[str, Any] = {}

    path = Path(csv_path)
    if not path.exists():
        msg = f"CSV not found: {csv_path}"
        raise FileNotFoundError(msg)

    encoding = detect_encoding(path)
    logger.info("Detected encoding: %s", encoding)

    df = pd.read_csv(
        path,
        sep=";",
        encoding=encoding,
        low_memory=False,
        dtype_backend="numpy_nullable",
    )

    exclusion_log["input"] = {
        "rows": len(df),
        "columns": list(df.columns),
        "encoding": encoding,
    }

    verify_and_log_pii(df, exclusion_log)

    pii_columns = [
        c
        for c in exclusion_log.get("pii_columns", {})
        if exclusion_log["pii_columns"][c] == "present_and_stripped"
    ]
    df = df.drop(columns=[c for c in pii_columns if c in df.columns], errors="ignore")

    df = select_columns(df, exclusion_log)

    con = duckdb.connect(":memory:")
    try:
        con.register("srag", df)

        source_csv_hash = compute_sha256(path)
        source_extraction_date = _extraction_date_from_filename(path)

        exclusion_log["output"] = {
            "rows": len(df),
            "columns": list(df.columns),
        }

        return {
            "con": con,
            "exclusion_log": exclusion_log,
            "source_csv_hash": source_csv_hash,
            "source_extraction_date": source_extraction_date,
        }
    except Exception:
        con.close()
        raise


def _extraction_date_from_filename(path: Path) -> str:
    """Extract YYYY-MM-DD from filename or return ``"unknown"``.

    Uses regex ``r"(\\d{2})-(\\d{2})-(\\d{4})\\.csv"`` to find the trailing
    date pattern, robust against varying dash counts in the prefix.

    Args:
        path: Path whose stem contains a date like ``DD-MM-YYYY``.

    Returns:
        Date string ``"YYYY-MM-DD"`` or ``"unknown"`` if not parseable.
    """
    match = _EXTRACTION_DATE_RE.search(path.name)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return "unknown"
