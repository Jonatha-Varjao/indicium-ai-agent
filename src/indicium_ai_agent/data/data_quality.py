from __future__ import annotations

from typing import Any

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


def detect_encoding(path: str) -> str:
    import chardet

    with open(path, "rb") as f:
        raw = f.read(100000)
    result = chardet.detect(raw)
    encoding = result["encoding"] or "latin-1"
    if encoding.lower() in ("ascii", "utf-8"):
        encoding = "latin-1"
    return encoding


def verify_and_log_pii(df: Any, exclusion_log: dict) -> dict:
    pii_findings: dict[str, str] = {}
    for col in PII_COLUMNS:
        if col in df.columns:
            pii_findings[col] = "present_and_stripped"
        else:
            pii_findings[col] = "already_absent"
    exclusion_log["pii_columns"] = pii_findings
    return exclusion_log


def select_columns(df: Any, exclusion_log: dict) -> Any:
    kept = [c for c in SELECTED_COLUMNS if c in df.columns]
    dropped = [c for c in SELECTED_COLUMNS if c not in df.columns]
    if dropped:
        exclusion_log["columns_not_found"] = {
            "reason": "columns defined in SELECTED_COLUMNS not present in file",
            "columns": dropped,
        }
    return df[kept]
