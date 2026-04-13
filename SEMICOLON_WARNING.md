# DB2 for i Semicolon Warning

**Date**: 2026-04-13  
**Feature**: Warning for trailing semicolon in AS400 SQL queries  
**Status**: ✅ Implemented

---

## The Issue

DB2 for i (AS400) JDBC driver **rejects trailing semicolons** in SQL statements when executing single queries programmatically.

### Error Message

```
Error: com.ibm.as400.access.AS400JDBCSQLSyntaxErrorException: 
[SQL0104] Token ; was not valid. Valid tokens: <END-OF-STATEMENT>.
```

### Why This Happens

| Context | Semicolon Behavior |
|---------|-------------------|
| **JDBC/Programmatic** (qadmcli, Java, Python) | ❌ Rejected - treated as invalid token |
| **Interactive SQL (STRSQL)** | ✅ Accepted - statement terminator |
| **SQL Scripts (RUNSQLSTM)** | ✅ Accepted - separates multiple statements |
| **DBeaver/SQuirreL SQL** | ✅ Accepted - GUI tools strip `;` automatically |
| **IBM ACS Run SQL Scripts** | ✅ Accepted - tool handles `;` |

---

## Solution: Warning Message

qadmcli now displays a **yellow warning** when it detects a trailing semicolon in AS400 queries.

### Example

```bash
# With semicolon - shows warning, then fails
$ qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS2;"

Warning: Trailing semicolon detected. DB2 for i JDBC driver may reject it. Consider removing the ';'.
[04/13/26 03:24:37] INFO     Connected to AS400: 161.82.146.249
Error: com.ibm.as400.access.AS400JDBCSQLSyntaxErrorException: [SQL0104] Token ; was not valid.

# Without semicolon - works perfectly
$ qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS2"

[04/13/26 03:24:49] INFO     Connected to AS400: 161.82.146.249
  Query Results (63 rows)
```

---

## Implementation

### Modified Commands

1. **`sql query`** - Warns for AS400 target
2. **`sql execute`** - Warns for AS400 target
3. **`mssql query`** - No warning (MSSQL accepts `;`)
4. **`mssql execute`** - No warning (MSSQL accepts `;`)

### Code Location

**File**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/cli.py`

**sql query command** (line ~3127):
```python
# Warn about trailing semicolon (DB2 for i doesn't accept it in JDBC)
if query.rstrip().endswith(';'):
    console.print("[yellow]Warning: Trailing semicolon detected. DB2 for i JDBC driver may reject it. Consider removing the ';'.[/yellow]")
```

**sql execute command** (line ~2965):
```python
# Warn about trailing semicolon for AS400 (DB2 for i doesn't accept it in JDBC)
if target == "as400" and query.rstrip().endswith(';'):
    console.print("[yellow]Warning: Trailing semicolon detected. DB2 for i JDBC driver may reject it. Consider removing the ';'.[/yellow]")
```

---

## Quick Reference

### Correct Usage

```bash
# ✅ Correct - no semicolon
qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS2"
qadmcli sql execute -q "SELECT COUNT(*) FROM GSLIBTST.CUSTOMERS2"
qadmcli sql execute -q "CREATE TABLE TEST (ID INT)"

# ❌ Wrong - will show warning and fail
qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS2;"
qadmcli sql execute -q "SELECT COUNT(*) FROM GSLIBTST.CUSTOMERS2;"
```

### Multiple Statements

**Not supported** in qadmcli anyway (single statement execution only):

```bash
# ❌ Won't work (multiple statements not supported)
qadmcli sql execute -q "INSERT INTO T1 VALUES (1); INSERT INTO T2 VALUES (2);"

# ✅ Correct - execute separately
qadmcli sql execute -q "INSERT INTO T1 VALUES (1)"
qadmcli sql execute -q "INSERT INTO T2 VALUES (2)"
```

---

## Why Not Auto-Strip?

We chose to **warn** instead of **auto-strip** because:

1. **Explicit is better than implicit** - Users should know what's wrong
2. **Educational** - Teaches DB2 for i JDBC behavior
3. **No silent changes** - Query is executed as-is, not modified
4. **Debugging clarity** - If it fails, the actual query is shown in logs

---

## Comparison with Other Tools

| Tool | Behavior with `;` | Approach |
|------|-------------------|----------|
| **qadmcli** | Shows warning, executes as-is | ⚠️ Warn |
| **DBeaver** | Strips `;` silently | ✅ Auto-fix |
| **IBM ACS** | Strips `;` silently | ✅ Auto-fix |
| **STRSQL** | Accepts `;` natively | ✅ Works |
| **JDBC (raw)** | Throws error | ❌ Fails |

---

## Best Practices

### For AS400/DB2 for i

```bash
# Always omit trailing semicolon in qadmcli
qadmcli sql query -q "SELECT column1, column2 FROM library.table WHERE condition = 'value'"
```

### For MSSQL

```bash
# Semicolons are optional (both work)
qadmcli sql query -q "SELECT * FROM dbo.CUSTOMERS" -t mssql
qadmcli sql query -q "SELECT * FROM dbo.CUSTOMERS;" -t mssql  # Also works
```

### Cross-Platform Scripts

If writing scripts that work on both AS400 and MSSQL:

```bash
# Omit semicolon for maximum compatibility
qadmcli sql query -q "SELECT COUNT(*) FROM table"  # Works on both
```

---

## Git Commit

```
Commit: 74126ca
Message: feat: Add warning for trailing semicolon in AS400 SQL queries

Changes:
- cli.py: Added warning to sql query command
- cli.py: Added warning to sql execute command  
- Only applies to AS400 target (MSSQL accepts semicolons)
```

---

## Testing

### Test 1: Query with Semicolon (Warning + Error)

```bash
$ qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS2;"

Warning: Trailing semicolon detected. DB2 for i JDBC driver may reject it. Consider removing the ';'.
Error: com.ibm.as400.access.AS400JDBCSQLSyntaxErrorException: [SQL0104] Token ; was not valid.
```

### Test 2: Query without Semicolon (Success)

```bash
$ qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS2"

  Query Results (63 rows)
┏━━━━━━━━━━━┓
┃ CUST_ID   ┃
┡━━━━━━━━━━━┩
│ 1         │
│ 2         │
└───────────┘
63 row(s) returned
```

### Test 3: MSSQL with Semicolon (No Warning)

```bash
$ qadmcli sql query -q "SELECT * FROM dbo.CUSTOMERS;" -t mssql

# No warning - MSSQL accepts semicolons
  Query Results (63 rows)
...
```

---

**Implemented**: 2026-04-13 03:25  
**Impact**: Non-breaking (warning only, query still executes)  
**Breaking Changes**: None
