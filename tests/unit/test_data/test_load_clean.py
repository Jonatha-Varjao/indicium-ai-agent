from __future__ import annotations

from pathlib import Path

import pandas as pd

from indicium_ai_agent.data.load_clean import load_and_clean


def _make_csv(tmp_path: Path, columns: list[str] | None = None) -> Path:
    data = {
        "DT_SIN_PRI": ["2026-01-01"],
        "DT_NOTIFIC": ["2026-01-02"],
        "DT_DIGITA": ["2026-01-03"],
        "DT_EVOLUCA": [""],
        "DT_INTERNA": [""],
        "DT_ENTUTI": [""],
        "DT_SAIDUTI": [""],
        "EVOLUCAO": [1],
        "HOSPITAL": [1],
        "UTI": [2],
        "CLASSI_FIN": [4],
        "VACINA_COV": [1],
        "VACINA": [2],
        "SG_UF": ["SP"],
        "SG_UF_NOT": ["SP"],
        "NU_IDADE_N": [30],
        "TP_IDADE": [3],
        "CS_SEXO": ["M"],
        "SEM_PRI": [1],
        "SEM_NOT": [1],
    }
    df = pd.DataFrame(data)
    if columns is not None:
        extra = {c: [""] for c in columns if c not in data}
        if extra:
            df = pd.concat([df, pd.DataFrame(extra)], axis=1)
    csv = tmp_path / "INFLUD26-20-07-2026.csv"
    df.to_csv(csv, sep=";", index=False)
    return csv


def test_basic_load(tmp_path: Path) -> None:
    csv = _make_csv(tmp_path)
    result = load_and_clean(str(csv))
    con = result["con"]
    rows = con.execute("SELECT COUNT(*) FROM srag").fetchone()[0]
    assert rows == 1
    assert result["source_extraction_date"] == "2026-07-20"


def test_pii_stripping(tmp_path: Path) -> None:
    csv = _make_csv(tmp_path, columns=["NU_CPF", "NM_PACIENT", "NU_CNS"])
    result = load_and_clean(str(csv))
    pii = result["exclusion_log"]["pii_columns"]
    assert pii["NU_CPF"] == "present_and_stripped"
    assert pii["NM_PACIENT"] == "present_and_stripped"
    assert pii["NU_CNS"] == "present_and_stripped"
    assert "NU_CPF" not in result["exclusion_log"]["output"]["columns"]
    assert "NM_PACIENT" not in result["exclusion_log"]["output"]["columns"]


def test_column_selection(tmp_path: Path) -> None:
    csv = _make_csv(tmp_path)
    result = load_and_clean(str(csv))
    cols = result["exclusion_log"]["output"]["columns"]
    assert "DT_SIN_PRI" in cols
    assert "EVOLUCAO" in cols
    assert "VACINA_COV" in cols
    assert "NU_CPF" not in cols


def test_missing_file_raises(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(FileNotFoundError, match="CSV not found"):
        load_and_clean(str(tmp_path / "nonexistent.csv"))


def test_duckdb_connection(tmp_path: Path) -> None:
    csv = _make_csv(tmp_path)
    result = load_and_clean(str(csv))
    con = result["con"]
    assert con is not None
    cols = con.execute("PRAGMA table_info('srag')").fetchall()
    col_names = [c[1] for c in cols]
    assert "DT_SIN_PRI" in col_names
