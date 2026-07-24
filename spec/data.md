# Data

## Sources

### Source A — Uploaded CSV Files

| Aspect | Detail |
|--------|--------|
| Format | Any text-separated CSV (semicolon, tab, pipe auto-detected via python csv Sniffer) |
| Max file size | 500 MB (hard cap enforced at upload) |
| Schema inference | `pandas.read_csv(nrows=1000)` then `df.dtypes` + sample distinct count per column |
| Storage | Normalised into a per-session SQLite table with randomised name; metadata stored in `csv_files` table |
| Retention | Temp tables are dropped when the parent run finishes or after 24 h TTL |
| Joins with DB | Column-name fuzzy match (levenshtein ≤ 2) + type-alignment check; analyst must confirm before cross-source query |

### Source B — Live MsSQL Police Database

| Aspect | Detail |
|--------|--------|
| Driver | `pyodbc` + MSOLEDB driver (Windows native) |
| Authentication | SQL Server auth or Windows Integrated; credential stored encrypted |
| User class | **Read-only SQL login** mandatory for all non-admin users |
| Schema cache | `sys.tables`, `sys.columns`, `sys.indexes` fetched on first connect; cached in-process 1 h TTL |
| Row caps | Officer default 10 000; analyst default 50 000; admin configurable |
| Timeout | 30 s hard timeout per statement; 120 s total per query run |
| Query type | All SQL is LLM-generated; no free-text SQL typing at the API |

## Schema

### SQLite — run history (existing `app.db`)

```sql
-- connexions (encrypted)
CREATE TABLE IF NOT EXISTS db_connections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    host        TEXT NOT NULL,
    port        INTEGER NOT NULL DEFAULT 1433,
    database    TEXT NOT NULL,
    username    TEXT NOT NULL,        -- encrypted
    -- password  NOT stored; credential derived from OS keyring or Fernet token
    encrypted_blob BLOB,              -- Fernet-encrypted (host+db+user+driver)
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS csv_files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    filename     TEXT NOT NULL,
    original_name TEXT NOT NULL,
    row_count    INTEGER,
    col_count    INTEGER,
    columns_json  TEXT,
    stored_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    role         TEXT NOT NULL CHECK(role IN ('officer','analyst','admin')),
    question     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    result_json  TEXT,
    error        TEXT,
    csv_ids      TEXT,                 -- JSON array
    db_conn_id   INTEGER,
    started_at   TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

-- Append-only audit log (immutable design intent)
CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT DEFAULT (datetime('now')),
    user_id   TEXT NOT NULL,
    run_id    TEXT NOT NULL,
    action    TEXT NOT NULL,
    detail    TEXT
);
```

## Retention & Compliance

| Data kind | Retention | Notes |
|-----------|-----------|-------|
| Run history / audit log | 90 days (hard-coded; prune via admin cron) | Tamper-evidencing achieved via append-only schema; future: write-ahead log to external store |
| Uploaded CSV temp tables | Until run completes + 24 h | Purged by background task on server start |
| DB credentials | Until user deletes | Encrypted at rest via Fernet; derive key from `AGENT_FERNET_KEY` env |
| LLM conversation log | Per-run, same TTL as run | Rotated with run |
