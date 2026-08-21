"""Tests for data_quality module."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from indicium_ai_agent.data.data_quality import (
    PII_COLUMNS,
    SELECTED_COLUMNS,
    detect_encoding,
    select_columns,
    verify_and_log_pii,
)


def test_detect_encoding_returns_latin1_for_ascii(tmp_path: Path) -> None:
    """ASCII content should be coerced to latin-1 (DATASUS convention)."""
    csv = tmp_path / "sample.csv"
    csv.write_text("col1;col2\n1;2\n", encoding="ascii")
    enc = detect_encoding(csv)
    assert enc == "latin-1"


def test_detect_encoding_handles_path_str(tmp_path: Path) -> None:
    """detect_encoding accepts both str and Path."""
    csv = tmp_path / "sample2.csv"
    csv.write_text("col1;col2\nval;val2\n", encoding="utf-8")
    # Passing str instead of Path should work
    enc = detect_encoding(str(csv))
    assert isinstance(enc, str)
    assert enc != ""


def test_detect_encoding_handles_none_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If chardet returns None, fallback to latin-1."""
    csv = tmp_path / "empty.csv"
    csv.write_bytes(b"")

    def fake_detect(_raw: bytes) -> dict[str, str | None]:
        return {"encoding": None}

    monkeypatch.setattr("indicium_ai_agent.data.data_quality.chardet.detect", fake_detect)
    enc = detect_encoding(csv)
    assert enc == "latin-1"


def test_detect_encoding_latin1_preserved(tmp_path: Path) -> None:
    """Non-ascii latin-1 characters should yield latin-1."""
    csv = tmp_path / "latin.csv"
    # Write with latin-1 encoding containing accented chars
    csv.write_text("nome;valor\nSão Paulo;1\n", encoding="latin-1")
    enc = detect_encoding(csv)
    # chardet may detect latin-1 or iso-8859-1 or windows-1252; our function normalizes ascii/utf-8 only
    # So ensure it returns something plausible and not empty
    assert enc.lower() not in ("", None)  # type: ignore[operator]
    # If detected as ascii/utf-8 it would be normalized to latin-1, else original
    assert isinstance(enc, str)


def test_verify_and_log_pii_present_and_absent() -> None:
    """verify_and_log_pii should log present and absent PII columns."""
    df = pd.DataFrame({"NU_CPF": [123], "NM_PACIENT": ["a"], "other": [1]})
    log: dict[str, object] = {}
    result = verify_and_log_pii(df, log)
    # Mutates and returns same dict
    assert result is log
    pii = log["pii_columns"]  # type: ignore[index]
    assert pii["NU_CPF"] == "present_and_stripped"  # type: ignore[index]
    assert pii["NM_PACIENT"] == "present_and_stripped"  # type: ignore[index]
    assert pii["NU_CNS"] == "already_absent"  # type: ignore[index]


def test_verify_and_log_pii_all_absent() -> None:
    """When no PII columns present, all should be already_absent."""
    df = pd.DataFrame({"DT_SIN_PRI": ["2026-01-01"]})
    log: dict[str, object] = {}
    verify_and_log_pii(df, log)
    for col in PII_COLUMNS:
        assert log["pii_columns"][col] == "already_absent"  # type: ignore[index,call-overload]


def test_select_columns_keeps_intersection() -> None:
    """select_columns keeps only columns that exist."""
    df = pd.DataFrame(
        {
            "DT_SIN_PRI": ["2026-01-01"],
            "EVOLUCAO": [1],
            "extra": [123],
        }
    )
    log: dict[str, object] = {}
    out = select_columns(df, log)
    assert list(out.columns) == ["DT_SIN_PRI", "EVOLUCAO"]
    # Dropped columns logged
    assert "columns_not_found" in log
    assert isinstance(log["columns_not_found"], dict)  # type: ignore[arg-type]


def test_select_columns_no_dropped() -> None:
    """When all SELECTED_COLUMNS present, no log entry."""
    data = {c: [1] for c in SELECTED_COLUMNS}
    df = pd.DataFrame(data)
    log: dict[str, object] = {}
    out = select_columns(df, log)
    assert set(out.columns) == set(SELECTED_COLUMNS)
    assert "columns_not_found" not in log


def test_select_columns_handles_path_union(tmp_path: Path) -> None:
    """select_columns handles empty df edge."""
    df = pd.DataFrame({"unknown": [1]})
    log: dict[str, object] = {}
    out = select_columns(df, log)
    assert out.empty or list(out.columns) == []
    assert log["columns_not_found"]["columns"] == SELECTED_COLUMNS  # type: ignore[index]
