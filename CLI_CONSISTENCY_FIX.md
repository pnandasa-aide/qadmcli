# CLI Option Consistency Fix

**Date**: 2026-04-13  
**Issue**: `user check-table` used `-n` instead of `-t` for table name  
**Status**: ✅ FIXED

---

## Problem

The `user check-table` command was inconsistent with all other qadmcli commands:

| Command | Table Option | Status |
|---------|--------------|--------|
| `mockup generate` | `-t` / `--table` | ✅ Consistent |
| `mssql ct status` | `-t` / `--table` | ✅ Consistent |
| `mssql ct changes` | `-t` / `--table` | ✅ Consistent |
| `mssql ct enable-table` | `-t` / `--table` | ✅ Consistent |
| `mssql ct disable-table` | `-t` / `--table` | ✅ Consistent |
| **`user check-table`** | **`-n` / `--name`** | **❌ Inconsistent** |

---

## Solution

Changed `user check-table` to use `-t` as the primary option while keeping `-n` as an alias for backward compatibility.

### Before

```bash
qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST
```

### After (Both Work)

```bash
# New standard way (recommended)
qadmcli user check-table -u GLUESYNC01 -t CUSTOMERS2 -l GSLIBTST

# Old way still works (backward compatible)
qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST
```

---

## Implementation

### Changed Files

**File**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/cli.py`

**Line 2110**: Updated option decorator
```python
# Before
@click.option("--name", "-n", required=True, help="Table name to check")

# After (supports both -t and -n)
@click.option("--table", "-t", "--name", "-n", required=True, help="Table name to check")
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
  -u, --user TEXT               Username to check  [required]
  -t, -n, --table, --name TEXT  Table name to check  [required]
  -l, --library TEXT            Library containing the table  [required]
  --help                        Show this message and exit.
```

Notice: `-t, -n, --table, --name` - all four options work!

---

## Testing

### Test with -t (New Standard)

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

### Test with -n (Backward Compatible)

```bash
$ qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST

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

✅ Both produce identical results!

---

## Benefits

1. **Consistency**: All table-related commands now use `-t`
2. **Memorability**: Users only need to remember one option flag
3. **Backward Compatibility**: Existing scripts using `-n` still work
4. **No Breaking Changes**: Both options are fully supported

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

**No action required!** Both `-t` and `-n` work.

However, for consistency in new scripts, prefer `-t`:

```bash
# Old (still works)
qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST

# New (recommended)
qadmcli user check-table -u GLUESYNC01 -t CUSTOMERS2 -l GSLIBTST
```

### For Documentation

Update any documentation or examples to use `-t` as the primary option.

---

**Fixed**: 2026-04-13 03:10  
**Impact**: None (backward compatible)  
**Breaking Changes**: None
