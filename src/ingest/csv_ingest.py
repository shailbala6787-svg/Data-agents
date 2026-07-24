"""CSV ingest helpers — pure, testable functions."""
from __future__ import annotations

import csv
import io
from pathlib import PurePosixPath
from typing import TypedDict

import pandas as pd
import sqlalchemy as sa

_NUMPY_TO_SQL = {
    "int64": "INTEGER",
    "int32": "INTEGER",
    "Int64": "INTEGER",
    "float64": "REAL",
    "float32": "REAL",
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "datetime64[ns]": "TIMESTAMP",
    "datetime64[ns, UTC]": "TIMESTAMP",
}


def detect_separator(sample_bytes: bytes) -> str:
    """Return the most-likely CSV separator; fall back to ','."""
    try:
        sample = sample_bytes[:4096].decode("latin-1", errors="replace")
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        return ","


class ColumnMeta(TypedDict):
    name: str
    type: str
    nullable: bool


def infer_schema(df: pd.DataFrame) -> list[ColumnMeta]:
    """Schema from a DataFrame. Handles pandas-renamed duplicate columns."""
    out: list[ColumnMeta] = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        sql_type = _NUMPY_TO_SQL.get(dtype, "TEXT")
        out.append(
            {
                "name": str(col),
                "type": sql_type,
                "nullable": bool(df[col].isna().any()),
            }
        )
    return out


def load_csv_to_sqlite(engine: sa.Engine, table_name: str, df: pd.DataFrame) -> None:
    """Write a DataFrame into `table_name`."""
    df.to_sql(table_name, engine, if_exists="replace", index=False)
