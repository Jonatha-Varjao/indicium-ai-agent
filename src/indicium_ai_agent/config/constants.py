"""Shared constants — single source of truth for cross-module values."""

from __future__ import annotations

from typing import Final

# Canonical metric keys — order matches metrics_spec.METRICS and render table
METRIC_KEYS: Final[tuple[str, ...]] = (
    "case_growth_rate",
    "mortality_rate",
    "uti_admission_rate",
    "vaccination_coverage",
)

# Max validation retries — used by narrative/validate.py and graph.py
MAX_RETRIES: Final[int] = 3

# Duration values the narrative may cite without numeric grounding:
# they come from documented methodology text, not computed data.
# - 7: rolling case-growth window (DEFAULT_GROWTH_DAYS semantics)
# - 14: sub-notification caveat upper bound ("últimos ~7-14 dias")
# - 30: daily chart window (últimos 30 dias)
KNOWN_DURATION_DAYS: Final[frozenset[int]] = frozenset({7, 14, 30})

# Chart rendering defaults
CHART_FIGSIZE: Final[tuple[int, int]] = (10, 4)
CHART_DPI: Final[int] = 150
