"""DuckDB warehouse: load tables and create the reference views."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .config import Config


def connect(path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path))


def load_tables(con: duckdb.DuckDBPyConnection, tables: dict[str, pd.DataFrame]) -> None:
    for name, df in tables.items():
        con.register(f"_stage_{name}", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _stage_{name}")
        con.unregister(f"_stage_{name}")


def build_warehouse(cfg: Config, reference: dict[str, pd.DataFrame], lines: pd.DataFrame,
                    path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    con = connect(path)
    lines = lines.copy()
    lines["order_ref"] = lines["order_ref"].astype("string")
    load_tables(con, {**reference, "invoice_lines": lines})
    con.execute((cfg.sql_dir / "00_views.sql").read_text())
    return con
