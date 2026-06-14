# AS400 Table Name Resolution Reference

IBM i (AS400) supports two names per table. This document catalogues
which system views use which name type and the proven fix patterns.

## Name Types

| Type | Max Length | Example | Column in SYSTABLES |
|---|---|---|---|
| **SQL name** | 128 chars | `DEMOTABLETEST_2` | `TABLE_NAME` |
| **System name** | 10 chars | `DEMOTABLETE` | `SYSTEM_TABLE_NAME` |

The system name is auto-truncated when the SQL name exceeds 10 characters.
System names must be uppercase and unique within a schema.

## View-by-View Reference

### QSYS2.SYSTABLES — Table Existence & Metadata

| Column | Name Type | Notes |
|---|---|---|
| `TABLE_NAME` | SQL | Full name, accepts long names |
| `SYSTEM_TABLE_NAME` | System | Truncated to 10 chars |
| `TABLE_SCHEMA` / `SYSTEM_TABLE_SCHEMA` | Both | Usually identical on modern IBM i |

**Pattern — match either name:**
```python
sql = """SELECT TABLE_NAME, TABLE_SCHEMA
         FROM QSYS2.SYSTABLES
         WHERE (TABLE_NAME = ? OR SYSTEM_TABLE_NAME = ?)
         AND TABLE_SCHEMA = ?"""
cursor.execute(sql, (name.upper(), name.upper(), lib.upper()))
```

**Pattern — resolve system name from SQL name:**
```python
cursor.execute(
    "SELECT SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES "
    "WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?",
    (table_name.upper(), library.upper())
)
system_name = str(row[0]).strip()  # 10-char name for downstream use
```

### QSYS2.JOURNALED_OBJECTS — Journal Status

| Column | Name Type | Notes |
|---|---|---|
| `OBJECT_NAME` | System | 10-char object name |
| `OBJECT_LIBRARY` | System | Library/ schema |
| `OBJECT_TYPE` | — | Always filter with `'*FILE'` |

**Pattern — query with both SQL and system name:**
```python
sql = """SELECT JOURNAL_LIBRARY, JOURNAL_NAME, JOURNAL_IMAGES
         FROM QSYS2.JOURNALED_OBJECTS
         WHERE (OBJECT_NAME = ? OR OBJECT_NAME = ?)
         AND OBJECT_LIBRARY = ?
         AND OBJECT_TYPE = '*FILE'"""
cursor.execute(sql, (sql_name, system_name, library.upper()))
```

### QSYS2.DISPLAY_JOURNAL — Journal Entry Filtering

| Column | Name Type | Notes |
|---|---|---|
| `OBJECT` | System | Inconsistent format: `"TBL LIB"` or `"TBL LIB  SYS_TBL"` |

**Pattern — use LIKE with system name prefix:**
```python
object_prefix = f"{system_name} {library.upper()}"
sql = """SELECT ... FROM TABLE(QSYS2.DISPLAY_JOURNAL(...))
         WHERE OBJECT LIKE ?"""
cursor.execute(sql, (f"{object_prefix}%",))
```

Never use `=` (exact match) — the trailing system name varies.

### QSYS2.SYSCOLUMNS / SYSCST / SYSKEYCST — Schema Metadata

| Column | Name Type | Notes |
|---|---|---|
| `TABLE_NAME` | SQL | Accepts long names directly |
| `TABLE_SCHEMA` | SQL | |

**No fallback needed** — these accept SQL names natively.

### QSYS2.SYSSCHEMAS — Schema-Level Journal Config

| Column | Name Type | Notes |
|---|---|---|
| `DEFAULT_JOURNAL_LIBRARY` | — | **DOES NOT EXIST** on some IBM i versions |
| `DEFAULT_JOURNAL_NAME` | — | **DOES NOT EXIST** on some IBM i versions |

**Pattern — wrap in exception handler:**
```python
try:
    cursor.execute("SELECT DEFAULT_JOURNAL_LIBRARY, DEFAULT_JOURNAL_NAME ...")
except Exception:
    result["auto_journal"] = False
    result["message"] = "Auto-journal check unavailable: columns not present"
```

### QSYS2.OBJECT_PRIVILEGES — Permission Check

| Column | Name Type | Notes |
|---|---|---|
| Various | — | Column names vary by IBM i version |

**Pattern — access by position, not column name:**
```python
row[0], row[1]  # positional, not row["COLUMN_NAME"]
```

## Summary Decision Table

| View / Function | Accepts SQL Name? | Accepts System Name? | Strategy |
|---|---|---|---|
| `SYSTABLES` (existence) | Yes (`TABLE_NAME`) | Yes (`SYSTEM_TABLE_NAME`) | OR both |
| `SYSTABLES` (system name resolve) | Yes (WHERE) | Yes (SELECT) | Query by SQL, read system |
| `JOURNALED_OBJECTS` | **No** | Yes | Resolve system name first, OR both |
| `DISPLAY_JOURNAL` | **No** | Yes (in OBJECT col) | LIKE with system name |
| `SYSCOLUMNS` | Yes | N/A | Direct SQL name |
| `SYSCST` / `SYSKEYCST` | Yes | N/A | Direct SQL name |
| `SYSSCHEMAS` | N/A | N/A | Guard missing columns |
| `OBJECT_PRIVILEGES` | N/A | N/A | Access by position |

## Quick Reference: The Resolution Chain

```
User provides "LIBRARY.TABLE_NAME" (SQL name, possibly >10 chars)
    │
    ▼
Query QSYS2.SYSTABLES with (TABLE_NAME = ? OR SYSTEM_TABLE_NAME = ?)
    │
    ├── Not found → error: table doesn't exist
    │
    └── Found → now we have SYSTEM_TABLE_NAME (10-char)
                    │
                    ▼
         Use SYSTEM name for:
           • QSYS2.JOURNALED_OBJECTS  (OBJECT_NAME)
           • QSYS2.DISPLAY_JOURNAL    (OBJECT LIKE)
           • Any other system-name-only view
```

## Files Using This Pattern

| File | Fix Applied |
|---|---|
| `qadmcli/src/qadmcli/db/journal.py` | SYSTABLES + JOURNALED_OBJECTS + DISPLAY_JOURNAL |
| `qadmcli/src/qadmcli/db/journal.py` | `_populate_table_entry_range()` — system name for DISPLAY_JOURNAL |
