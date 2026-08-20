"""Data quality helpers: encoding detection, PII verification, column selection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chardet
import pandas as pd

PII_COLUMNS: list[str] = [
    "NU_CPF",
    "NM_PACIENT",
    "NU_CNS",
    "NM_MAE_PAC",
    "NU_CEP",
    "NM_BAIRRO",
    "NM_LOGRADO",
    "NU_NUMERO",
    "NM_COMPLEM",
    "NU_DDD_TEL",
    "NU_TELEFON",
    "DT_NASC",
    "NOME_PROF",
    "REG_PROF",
]

SELECTED_COLUMNS: list[str] = [
    "DT_SIN_PRI",
    "DT_NOTIFIC",
    "DT_DIGITA",
    "DT_EVOLUCA",
    "DT_INTERNA",
    "DT_ENTUTI",
    "DT_SAIDUTI",
    "EVOLUCAO",
    "HOSPITAL",
    "UTI",
    "CLASSI_FIN",
    "VACINA_COV",
    "VACINA",
    "SG_UF",
    "SG_UF_NOT",
    "NU_IDADE_N",
    "TP_IDADE",
    "CS_SEXO",
    "SEM_PRI",
    "SEM_NOT",
]


def detect_encoding(path: str | Path) -> str:
    """Detect CSV file encoding.

    Uses ``chardet`` to guess encoding from the first 100 kB. DATASUS SRAG
    files are historically encoded in ``latin-1`` (ISO-8859-1), so ASCII/UTF-8
    detections are coerced to ``latin-1`` to preserve accented characters.

    Args:
        path: Path to the CSV file (``str`` or ``Path``).

    Returns:
        Detected encoding string (e.g. ``"latin-1"`` or ``"utf-8"``).
    """
    file_path = Path(path)
    with open(file_path, "rb") as f:
        raw = f.read(100000)
    result: Any = chardet.detect(raw)
    encoding: str | None = result.get("encoding")
    if encoding is None:
        return "latin-1"
    # DATASUS files declare latin-1; chardet often returns ascii for pure-ascii
    # samples which is compatible but we normalize to latin-1 for consistency.
    if encoding.lower() in ("ascii", "utf-8"):
        return "latin-1"
    return encoding


def verify_and_log_pii(
    df: pd.DataFrame,
    exclusion_log: dict[str, Any],
) -> dict[str, Any]:
    """Verify presence of PII columns and record findings.

    Mutates ``exclusion_log`` in-place by adding a ``"pii_columns"`` key and
    returns the same dict for convenience.

    Args:
        df: Input DataFrame to inspect.
        exclusion_log: Mutable log dict that will be updated.

    Returns:
        The same ``exclusion_log`` instance, now containing ``pii_columns``.
    """
    pii_findings: dict[str, str] = {}
    for col in PII_COLUMNS:
        if col in df.columns:
            pii_findings[col] = "present_and_stripped"
        else:
            pii_findings[col] = "already_absent"
    exclusion_log["pii_columns"] = pii_findings
    return exclusion_log


def select_columns(
    df: pd.DataFrame,
    exclusion_log: dict[str, Any],
) -> pd.DataFrame:
    """Select only ``SELECTED_COLUMNS`` present in ``df``.

    Mutates ``exclusion_log`` in-place if any selected columns are missing.

    Args:
        df: Input DataFrame.
        exclusion_log: Mutable log dict updated with missing columns info.

    Returns:
        DataFrame containing only the intersection of ``SELECTED_COLUMNS``
        and ``df.columns``.
    """
    kept = [c for c in SELECTED_COLUMNS if c in df.columns]
    dropped = [c for c in SELECTED_COLUMNS if c not in df.columns]
    if dropped:
        exclusion_log["columns_not_found"] = {
            "reason": "columns defined in SELECTED_COLUMNS not present in file",
            "columns": dropped,
        }
    return df[kept]
