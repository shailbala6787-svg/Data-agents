"""ConnectionManager — MsSQL profiles + CSV-temp-SQLite with schema cache."""
from __future__ import annotations

import json
import os
import pickle
import time
from typing import Any

import pandas as pd
import sqlalchemy as sa
from cryptography.fernet import Fernet, InvalidToken

_SCHEMA_CACHE_TTL_S = 3600
_TABLE_REG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".tmp_tables.json")

_ROLE_ROW_CAPS: dict[str, int] = {
 "officer": 10_000,
 "analyst": 50_000,
 "admin": 500_000,
}


def _load_registry() -> dict:
    try:
        with open(_TABLE_REG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_registry(reg: dict) -> None:
    os.makedirs(os.path.dirname(_TABLE_REG_PATH), exist_ok=True)
    with open(_TABLE_REG_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f)


def _touch(table_name: str, n_rows: int) -> None:
    reg = _load_registry()
    reg[table_name] = int(n_rows)
    _save_registry(reg)


class ConnectionManager:
    def __init__(self, ferkey: bytes | None = None, csv_max_bytes: int | None = None) -> None:
        self._f: Fernet | None = None
        if ferkey is not None:
            try:
                Fernet(ferkey)  # validate
                self._f = Fernet(ferkey)
            except Exception as exc:
                raise ValueError("AGENT_FERNET_KEY is not valid. Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key())'") from exc

        self._schema_cache: dict[tuple[str, int], dict[str, Any]] = {}
        self._csv_engine = sa.create_engine(
            "sqlite://", poolclass=sa.StaticPool, connect_args={"check_same_thread": False}, echo=False
        )
        try:
            from src.config.settings import get_settings

            self._csv_max_bytes = (
                csv_max_bytes if csv_max_bytes is not None else get_settings().csv_max_bytes
            )
        except Exception:
            self._csv_max_bytes = 500 * 1024 * 1024

    @property
    def _temp_tables(self) -> dict[str, int]:
        return _load_registry()

    # ---- helpers ----

    def _encrypt(self, payload: dict) -> bytes:
        blob = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        if self._f is None:
            return b"PLAIN:" + blob
        return self._f.encrypt(blob)

    def _decrypt(self, blob: bytes) -> dict:
        if blob.startswith(b"PLAIN:") or self._f is None:
            return pickle.loads(blob[6:] if blob.startswith(b"PLAIN:") else blob)
        try:
            return pickle.loads(self._f.decrypt(blob))
        except InvalidToken as exc:
            raise ValueError("Credential blob corrupt or key mismatch.") from exc

    @staticmethod
    def _row(row) -> dict:
        if row is None:
            return {}
        return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

    def _q(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        with self._run_engine.connect() as conn:
            return [self._row(r) for r in conn.execute(sa.text(sql), params).fetchall()]

    def _q1(self, sql: str, params: tuple | dict = ()) -> dict | None:
        with self._run_engine.connect() as conn:
            r = conn.execute(sa.text(sql), params).fetchone()
        return self._row(r)

    def _exec(self, sql: str, params: tuple | dict = ()) -> None:
        with self._run_engine.connect() as conn:
            conn.execute(sa.text(sql), params)
            conn.commit()

    @property
    def _run_engine(self) -> sa.Engine:
        from src.db.session import _get_run_engine
        return _get_run_engine()

    # ---- MsSQL profile CRUD ----

    def add_mssql_profile(
        self,
        user_id: str,
        name: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        driver: str = "{ODBC Driver 17 for SQL Server}",
    ) -> int:
        creds = self._encrypt({"host": host, "port": port, "database": database, "username": username, "password": password, "driver": driver})
        row = self._q1(
            "INSERT INTO db_connections (user_id, name, host, port, database, username, encrypted_blob) "
            "VALUES (:u,:n,:h,:p,:d,:un,:b) RETURNING id",
            {"u": user_id, "n": name, "h": host, "p": port, "d": database, "un": username, "b": creds},
        )
        return row["id"] if row else -1

    def list_profiles(self, user_id: str) -> list[dict]:
        return self._q("SELECT id, user_id, name, host, port, database, username, created_at FROM db_connections WHERE user_id = :u", {"u": user_id})

    def remove_profile(self, user_id: str, conn_id: int) -> None:
        self._exec("DELETE FROM db_connections WHERE id = :c AND user_id = :u", {"c": conn_id, "u": user_id})

    # ---- schema session ----

    def get_session(self, user_id: str, conn_id: int, role: str):
        cache_key = (user_id, conn_id)
        cached = self._schema_cache.get(cache_key)
        if cached and (time.time() - cached["ts"]) < _SCHEMA_CACHE_TTL_S:
            return cached["engine"], _ROLE_ROW_CAPS.get(role, 50_000), cached["schema"]

        row = self._q1("SELECT encrypted_blob FROM db_connections WHERE id = :c AND user_id = :u", {"c": conn_id, "u": user_id})
        if not row:
            raise ValueError(f"No MsSQL profile id={conn_id} for user {user_id}")

        creds = self._decrypt(row["encrypted_blob"])
        conn_str = (
            f"mssql+pyodbc://{creds['username']}:{creds['password']}@"
            f"{creds['host']}:{creds.get('port', 1433)}/{creds['database']}"
            f"?driver={creds.get('driver', '{ODBC Driver 17 for SQL Server}')}"
        )
        engine = sa.create_engine(conn_str, pool_pre_ping=True, pool_recycle=3600, pool_size=2, max_overflow=3)
        schema = self._load_schema(engine)

        self._schema_cache[cache_key] = {"ts": time.time(), "engine": engine, "schema": schema}
        return engine, _ROLE_ROW_CAPS.get(role, 50_000), schema

    @staticmethod
    def _load_schema(engine: sa.Engine) -> dict:
        schema: dict[str, Any] = {"tables": []}
        try:
            with engine.connect() as conn:
                rows = conn.execute(sa.text(
                    "SELECT t.name AS tname, c.name AS cname, ty.name AS dtype, c.is_nullable "
                    "FROM sys.tables t JOIN sys.columns c ON t.object_id=c.object_id "
                    "JOIN sys.types ty ON c.user_type_id=ty.user_type_id "
                    "ORDER BY t.name, c.column_id"
                )).fetchall()
            cur = None
            for r in rows:
                if cur is None or cur["name"] != r.tname:
                    cur = {"name": r.tname, "columns": []}
                    schema["tables"].append(cur)
                cur["columns"].append({"name": r.cname, "type": r.dtype, "nullable": bool(r.is_nullable)})
        except Exception as exc:
            schema["error"] = str(exc)
        return schema

    # ---- CSV temp table ops ----

    def csv_to_sqlite(self, csv_bytes: bytes, filename: str) -> tuple[str, int, list[dict]]:
        if len(csv_bytes) > self._csv_max_bytes:
            raise ValueError(
                f"CSV exceeds {self._csv_max_bytes // (1024 * 1024)} MB limit."
            )

        from src.ingest.csv_ingest import detect_separator, infer_schema, load_csv_to_sqlite

        sep = detect_separator(csv_bytes)

        try:
            df = pd.read_csv(
                pd.io.common.BytesIO(csv_bytes), sep=sep, on_bad_lines="skip", engine="python"
            )
        except Exception as exc:
            raise ValueError(f"CSV parse error: {exc}") from exc

        if df.empty:
            raise ValueError("CSV contains no parseable rows.")

        table_name = f"rnd_{abs(hash(filename)):012x}"
        cols = infer_schema(df)
        n_rows = len(df)
        load_csv_to_sqlite(self._csv_engine, table_name, df)
        _touch(table_name, n_rows)
        return table_name, n_rows, cols

    def drop_temp_table(self, table_name: str) -> None:
        if table_name in self._temp_tables:
            try:
                with self._csv_engine.connect() as conn:
                    conn.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}"'))
            except Exception:
                pass
            reg = _load_registry()
            reg.pop(table_name, None)
            _save_registry(reg)

    def cleanup_temp_tables(self) -> None:
        for t in list(self._temp_tables):
            self.drop_temp_table(t)

    def query_sqlite_temp(self, table_name: str, sql: str, row_cap: int) -> pd.DataFrame:
        if table_name not in self._temp_tables:
            raise ValueError(f"Unknown temp table: {table_name}")
        capped = f"SELECT * FROM ({sql}) AS _upc LIMIT {row_cap}"
        with self._csv_engine.connect() as conn:
            return pd.read_sql(sa.text(capped), conn)
