from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


def _daily_cases(con: duckdb.DuckDBPyConnection, end_date: date) -> plt.Figure:
    start = end_date - timedelta(days=30)
    query = """
        SELECT CAST(DT_SIN_PRI AS DATE) AS data, COUNT(*) AS casos
        FROM srag
        WHERE CAST(DT_SIN_PRI AS DATE) >= CAST(? AS DATE)
          AND CAST(DT_SIN_PRI AS DATE) < CAST(? AS DATE)
        GROUP BY CAST(DT_SIN_PRI AS DATE)
        ORDER BY data
    """
    df = con.execute(query, [start.isoformat(), end_date.isoformat()]).fetchdf()

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(pd.to_datetime(df["data"]), df["casos"], marker="o", linestyle="-", linewidth=1)
    ax.set_title("Número diário de casos — últimos 30 dias")
    ax.set_xlabel("Data")
    ax.set_ylabel("Casos")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def _monthly_cases(con: duckdb.DuckDBPyConnection, end_date: date) -> plt.Figure:
    start = end_date - timedelta(days=365)
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
    df = con.execute(query, [start.isoformat(), end_date.isoformat()]).fetchdf()

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(range(len(df)), df["casos"], width=0.7)
    ax.set_title("Número mensal de casos — últimos 12 meses")
    ax.set_xlabel("Mês")
    ax.set_ylabel("Casos")
    ax.set_xticks(range(len(df)))
    labels: list[str] = pd.to_datetime(df["mes"]).dt.strftime("%b/%Y").to_list() if not df.empty else []
    ax.set_xticklabels(labels, rotation=45, ha="right")
    fig.tight_layout()
    return fig


def generate_charts(
    con: duckdb.DuckDBPyConnection,
    output_dir: Path,
    end_date_str: str | None = None,
) -> dict[str, str]:
    import datetime as dt

    end = date.fromisoformat(end_date_str) if end_date_str else dt.datetime.now(dt.UTC).date()

    output_dir.mkdir(parents=True, exist_ok=True)

    fig_daily = _daily_cases(con, end)
    daily_path = output_dir / "daily_cases.png"
    fig_daily.savefig(daily_path, dpi=150)
    plt.close(fig_daily)

    fig_monthly = _monthly_cases(con, end)
    monthly_path = output_dir / "monthly_cases.png"
    fig_monthly.savefig(monthly_path, dpi=150)
    plt.close(fig_monthly)

    return {
        "daily": str(daily_path),
        "monthly": str(monthly_path),
    }
