from __future__ import annotations

METRICS: dict[str, dict] = {
    "case_growth_rate": {
        "name": "Taxa de aumento de casos",
        "definition": (
            "(casos últimos 7 dias − casos 7 dias anteriores) "
            "/ casos 7 dias anteriores × 100"
        ),
        "formula_ref": "case_growth_rate_v1",
        "anchor_column": "DT_SIN_PRI",
        "window": "rolling_7d_vs_prior_7d",
        "caveat": (
            "Os últimos ~7–14 dias podem estar subnotificados "
            "(atraso de notificação)."
        ),
        "return_shape": {
            "value": "float | None",
            "computable": "bool",
            "numerator": "int",
            "denominator": "int",
            "period": "str",
            "definition_ref": "str",
            "query": "str",
        },
    },
    "mortality_rate": {
        "name": "Taxa de mortalidade",
        "definition": (
            "óbitos / (óbitos + curas) usando EVOLUCAO "
            "(2=óbito por SRAG, 1=cura); "
            "EVOLUCAO=3 (óbito por outras causas) excluído "
            "do numerador e denominador"
        ),
        "formula_ref": "mortality_rate_v1",
        "evolucao_codes": {
            "cure": 1,
            "death_srag": 2,
            "death_other_causes": 3,
            "ignored": 9,
            "excluded_from_both": [3, 9],
        },
        "window": "configurable — default 12 meses",
        "caveat": (
            "Casos com EVOLUCAO=3 (óbito por outras causas) "
            "e EVOLUCAO=9 (ignorado) são excluídos "
            "do denominador."
        ),
        "return_shape": {
            "value": "float | None",
            "computable": "bool",
            "numerator": "int",
            "denominator": "int",
            "period": "str",
            "definition_ref": "str",
            "query": "str",
        },
    },
    "uti_admission_rate": {
        "name": "Taxa de internação em UTI entre casos de SRAG",
        "definition": (
            "casos com UTI=1 (Sim) / total casos com HOSPITAL=1 "
            "(internados). Relabeled from 'taxa de ocupação' because "
            "the dataset supports admission rate only, not concurrent "
            "bed occupancy."
        ),
        "formula_ref": "uti_admission_rate_v1",
        "fields": ["UTI", "HOSPITAL"],
        "window": "configurable — default 12 meses",
        "caveat": (
            "Reflete a proporção de casos hospitalizados que "
            "necessitaram de UTI, não a ocupação de leitos."
        ),
        "return_shape": {
            "value": "float | None",
            "computable": "bool",
            "numerator": "int",
            "denominator": "int",
            "period": "str",
            "definition_ref": "str",
            "query": "str",
        },
    },
    "vaccination_coverage": {
        "name": "Taxa de vacinação",
        "definition": (
            "Cobertura vacinal populacional via DATASUS/PNI "
            "por UF/período. Reportada separadamente para "
            "COVID-19 (VACINA_COV) e Influenza (VACINA)."
        ),
        "formula_ref": "vaccination_coverage_v1",
        "fields": ["VACINA_COV", "VACINA"],
        "data_source": "DATASUS/PNI",
        "fallback": (
            "Se o join PNI não estiver disponível, reporta "
            "'proporção de casos hospitalizados com esquema "
            "vacinal completo' para cada patógeno, "
            "explicitamente rotulada como cobertura "
            "hospitalar, não populacional."
        ),
        "window": "conforme periodicidade dos dados PNI",
        "caveat": (
            "Duas taxas separadas, uma por patógeno. "
            "Nunca conflacionadas em um único número."
        ),
        "return_shape": {
            "value": "dict | None",
            "computable": "bool",
            "numerator": "dict",
            "denominator": "int",
            "period": "str",
            "definition_ref": "str",
            "query": "str",
        },
    },
}

CHART_SPECS: dict[str, dict] = {
    "daily_cases": {
        "name": "Número diário de casos — últimos 30 dias",
        "window": "30 dias",
        "type": "line",
        "anchor_column": "DT_SIN_PRI",
    },
    "monthly_cases": {
        "name": "Número mensal de casos — últimos 12 meses",
        "window": "12 meses",
        "type": "bar",
        "anchor_column": "DT_SIN_PRI",
    },
}
