"""Chart generation for SRAG case data."""

from __future__ import annotations

import datetime
from datetime import date, timedelta
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure

from indicium_ai_agent.config.constants import CHART_DPI, CHART_FIGSIZE


def _fetch_cases(
    con: duckdb.DuckDBPyConnection,
    start: date,
    end: date,
    trunc: str | None = None,
) -> pd.DataFrame:
    """Fetch case counts from DuckDB.

    Args:
        con: DuckDB connection with ``srag`` table.
        start: Inclusive start date.
        end: Exclusive end date.
        trunc: If ``"month"``, aggregate by month; otherwise by day.

    Returns:
        DataFrame with date column (``data`` or ``mes``) and ``casos`` count.

    """
    if trunc == "month":
        query = """
            SELECT
                DATE_TRUNC('month', CAST(DT_SIN_PRI AS DATE)) AS mes,
                COUNT(*) AS casos
            FROM srag
            WHERE CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
              AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
            GROUP BY DATE_TRUNC('month', CAST(DT_SIN_PRI AS DATE))
            ORDER BY mes
        """
    else:
        query = """
            SELECT CAST(DT_SIN_PRI AS DATE) AS data, COUNT(*) AS casos
            FROM srag
            WHERE CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
              AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
            GROUP BY CAST(DT_SIN_PRI AS DATE)
            ORDER BY data
        """
    df: pd.DataFrame = con.execute(query, [start.isoformat(), end.isoformat()]).fetchdf()
    return df


def _daily_cases(con: duckdb.DuckDBPyConnection, end_date: date) -> Figure:
    """Generate daily cases figure for the last 30 days.

    Args:
        con: DuckDB connection.
        end_date: Exclusive end date for the 30-day window.

    Returns:
        Matplotlib Figure with daily case line plot.

    """
    start = end_date - timedelta(days=30)
    df: pd.DataFrame = _fetch_cases(con, start, end_date)

    fig, ax = plt.subplots(figsize=CHART_FIGSIZE)
    if df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        fig.tight_layout()
        return fig

    ax.plot(pd.to_datetime(df["data"]), df["casos"], marker="o", linestyle="-", linewidth=1)
    ax.set_title("Número diário de casos — últimos 30 dias")
    ax.set_xlabel("Data")
    ax.set_ylabel("Casos")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))  # type: ignore[no-untyped-call]
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def _monthly_cases(con: duckdb.DuckDBPyConnection, end_date: date) -> Figure:
    """Generate monthly cases figure for the last 12 months.

    Args:
        con: DuckDB connection.
        end_date: Exclusive end date for the 12-month window.

    Returns:
        Matplotlib Figure with monthly case bar chart.

    """
    start = end_date - timedelta(days=365)
    df: pd.DataFrame = _fetch_cases(con, start, end_date, trunc="month")

    fig, ax = plt.subplots(figsize=CHART_FIGSIZE)
    ax.bar(range(len(df)), df["casos"], width=0.7)
    ax.set_title("Número mensal de casos — últimos 12 meses")
    ax.set_xlabel("Mês")
    ax.set_ylabel("Casos")
    ax.set_xticks(range(len(df)))
    labels: list[str] = (
        pd.to_datetime(df["mes"]).dt.strftime("%b/%Y").to_list() if not df.empty else []
    )
    ax.set_xticklabels(labels, rotation=45, ha="right")
    fig.tight_layout()
    return fig


def _save_figure(fig: Figure, path: Path) -> None:
    """Save figure to disk with error handling.

    Args:
        fig: Figure to save.
        path: Destination file path.

    Raises:
        OSError: If saving fails (e.g., disk full).

    """
    try:
        fig.savefig(path, dpi=CHART_DPI)
    except OSError as exc:
        raise OSError(f"Failed to save chart to {path}: {exc}") from exc
    finally:
        plt.close(fig)


def generate_charts(
    con: duckdb.DuckDBPyConnection,
    output_dir: Path,
    end_date_str: str | None = None,
) -> dict[str, str]:
    """Generate daily and monthly case charts.

    Args:
        con: DuckDB connection with ``srag`` table.
        output_dir: Directory to write PNG files.
        end_date_str: ISO date string for exclusive end date; defaults to today UTC.

    Returns:
        Mapping with ``daily`` and ``monthly`` file paths as strings.

    Raises:
        OSError: If output directory creation or chart saving fails.

    """
    end = (
        date.fromisoformat(end_date_str)
        if end_date_str
        else datetime.datetime.now(datetime.UTC).date()
    )

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"Failed to create output directory {output_dir}: {exc}") from exc

    fig_daily = _daily_cases(con, end)
    daily_path = output_dir / "daily_cases.png"
    _save_figure(fig_daily, daily_path)

    fig_monthly = _monthly_cases(con, end)
    monthly_path = output_dir / "monthly_cases.png"
    _save_figure(fig_monthly, monthly_path)

    return {
        "daily": str(daily_path),
        "monthly": str(monthly_path),
    }
