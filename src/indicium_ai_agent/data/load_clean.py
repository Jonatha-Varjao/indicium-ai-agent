from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from indicium_ai_agent.data import compute_sha256
from indicium_ai_agent.data.data_quality import (
    detect_encoding,
    select_columns,
    verify_and_log_pii,
)

logger = logging.getLogger(__name__)


def load_and_clean(csv_path: str) -> dict[str, Any]:
    exclusion_log: dict[str, Any] = {}

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    encoding = detect_encoding(str(path))
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
        c for c in exclusion_log.get("pii_columns", {})
        if exclusion_log["pii_columns"][c] == "present_and_stripped"
    ]
    df = df.drop(columns=[c for c in pii_columns if c in df.columns], errors="ignore")

    df = select_columns(df, exclusion_log)

    con = duckdb.connect(":memory:")
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


def _extraction_date_from_filename(path: Path) -> str:
    name = path.stem
    parts = name.split("-")
    if len(parts) >= 3:
        try:
            day, month, year = parts[-3], parts[-2], parts[-1]
            if len(day) == 2 and len(month) == 2 and len(year) == 4:
                return f"{year}-{month}-{day}"
        except (ValueError, IndexError):
            pass
    return "unknown"
