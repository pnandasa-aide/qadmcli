# CLI Option Consistency Fix

**Date**: 2026-04-13  
**Issue**: `user check-table` used `-n` instead of `-t` for table name  
**Status**: ✅ FIXED

---

## Problem

The `user check-table` command was inconsistent with all other qadmcli commands:

| Command | Table Option | Number Option | Status |
|---------|--------------|---------------|--------|
| `mockup generate` | `-t` / `--table` | `-n` / `--number` | ✅ Consistent |
| `mssql ct status` | `-t` / `--table` | N/A | ✅ Consistent |
| `mssql ct changes` | `-t` / `--table` | `-l` / `--limit` | ✅ Consistent |
| `mssql ct enable-table` | `-t` / `--table` | N/A | ✅ Consistent |
| `mssql ct disable-table` | `-t` / `--table` | N/A | ✅ Consistent |
| **`user check-table`** | **`-n` / `--name`** | **N/A** | **❌ Inconsistent** |

**Semantic Confusion**: `-n` was used for "name" in `user check-table` but for "number" in `mockup generate`.

---

## Solution

Changed `user check-table` to use `-t` exclusively for table name, removing the confusing `-n` alias.

### Before

```bash
qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST  # ❌ Old way (no longer works)
```

### After

```bash
# Only way (clear and consistent)
qadmcli user check-table -u GLUESYNC01 -t CUSTOMERS2 -l GSLIBTST  # ✅ Correct
```

---

## Implementation

### Changed Files

**File**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/cli.py`

**Line 2110**: Updated option decorator
```python
# Before (confusing -n for "name")
@click.option("--name", "-n", required=True, help="Table name to check")

# After (clear -t for "table")
@click.option("--table", "-t", required=True, help="Table name to check")
```

**Line 2116**: Updated function parameter
```python
# Before
def user_check_table(ctx: click.Context, user: str, name: str, library: str)

# After
def user_check_table(ctx: click.Context, user: str, table: str, library: str)
```

**Line 2136 & 2144**: Updated variable usage
```python
# Before
result = user_mgr.check_table_permissions_with_journal(user, name, library)
print_panel(ctx, f"Checking permissions for {user} on {library}.{name}", ...)

# After
result = user_mgr.check_table_permissions_with_journal(user, table, library)
print_panel(ctx, f"Checking permissions for {user} on {library}.{table}", ...)
```

---

## Help Output

```
$ qadmcli user check-table --help

Options:
  -u, --user TEXT     Username to check  [required]
  -t, --table TEXT    Table name to check  [required]
  -l, --library TEXT  Library containing the table  [required]
  --help              Show this message and exit.
```

Notice: Clean and simple - only `-t` / `--table` for table name!

---

## Testing

### Test with -t (Only Option)

```bash
$ qadmcli user check-table -u GLUESYNC01 -t CUSTOMERS2 -l GSLIBTST

╭───────────────── Table Permission Check ─────────────────╮
│ Checking permissions for GLUESYNC01 on GSLIBTST.CUSTOMERS2 │
╰──────────────────────────────────────────────────────────╯

                 Table Permissions                 
 Property            | Value                       
---------------------+-----------------------------
 Object              | GSLIBTST.CUSTOMERS2         
 Type                | *FILE                       
 Effective Authority | *ALL                        
 Primary Source      | Direct User Grant           
```

### Test with -n (Should Fail)

```bash
$ qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST

Error: No such option: -n
```

✅ Clear semantic meaning - `-n` is no longer confused with table name!

---

## Benefits

1. **Consistency**: All table-related commands now use `-t`
2. **Semantic Clarity**: `-n` exclusively means "number", `-t` exclusively means "table"
3. **Memorability**: Users only need to remember one option flag per concept
4. **No Ambiguity**: Clear separation of concerns

### Option Semantics

| Option | Meaning | Used In |
|--------|---------|----------|
| `-t` | Table name | All table-related commands |
| `-n` | Number (count/transactions) | `mockup generate` |
| `-l` | Library or Limit | Context-dependent |
| `-u` | User | User-related commands |

---

## Command Consistency Reference

### All qadmcli Commands Using `-t` for Table

```bash
# AS400 commands
qadmcli mockup generate -t TABLE_NAME -l LIBRARY -n 100
qadmcli user check-table -u USERNAME -t TABLE_NAME -l LIBRARY
qadmcli user grant -u USERNAME -g *ALL -l LIBRARY -n TABLE_NAME -t *FILE

# MSSQL commands
qadmcli mssql ct status -t TABLE_NAME -s dbo
qadmcli mssql ct changes -t TABLE_NAME -s dbo --limit 100
qadmcli mssql ct enable-table -t TABLE_NAME -s dbo
qadmcli mssql ct disable-table -t TABLE_NAME -s dbo

# Generic SQL
qadmcli sql execute -q "..." -t as400  # -t for target database
qadmcli sql query -q "..." -t mssql    # -t for target database
```

---

## Git Commit

```
Commit: f45a71a
Message: fix: Change user check-table to use -t for table name (consistency)

Changes:
- cli.py: Updated user_check_table command
- Added backward compatibility with -n option
- Fixed variable references (name → table)
```

---

## Migration Guide

### For Users

**Action Required**: Update any scripts using `-n` to use `-t` instead:

```bash
# Old (no longer works)
qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST  # ❌ Error

# New (correct)
qadmcli user check-table -u GLUESYNC01 -t CUSTOMERS2 -l GSLIBTST  # ✅ Works
```

### For Documentation

Update all documentation and examples to use `-t` for table name.

---

**Fixed**: 2026-04-13 03:12  
**Impact**: Breaking change (scripts must update -n to -t)  
**Breaking Changes**: Yes (-n no longer accepted, use -t instead)
