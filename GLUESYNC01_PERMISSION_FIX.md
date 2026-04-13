# GLUESYNC01 Permission Issue - Resolved

**Date**: 2026-04-13  
**Issue**: Query hanging on CUSTOMERS2 table  
**Status**: ✅ RESOLVED

---

## Problem

When running queries on `GSLIBTST.CUSTOMERS2` table, the query would hang indefinitely:

```bash
qadmcli sql execute -q "SELECT OBJECT_NAME, OBJECT_AUTHORITY, DATA_READ, DATA_UPDATE 
FROM QSYS2.OBJECT_PRIVILEGES 
WHERE AUTHORIZATION_NAME = 'GLUESYNC01' AND OBJECT_NAME = 'CUSTOMERS2'"
```

**Symptom**: Query hangs, no rows returned, eventually times out

---

## Root Cause

GLUESYNC01 user had **`*EXCLUDE`** authority on CUSTOMERS2 table.

### Permission Check Results (BEFORE fix):

```
╭───────────────── Table Permissions ─────────────────╮
│ Object              | GSLIBTST.CUSTOMERS2           │
│ Type                | *FILE                         │
│ Effective Authority | *EXCLUDE ❌                    │
│ Primary Source      | *PUBLIC                       │
│ Authority Details   | - *PUBLIC: *EXCLUDE           │
╰─────────────────────────────────────────────────────╯
```

**Why the query hung**:
1. The user didn't have read permission on the table
2. The database was waiting for authorization that would never come
3. No timeout was set, so it waited indefinitely

---

## Solution

### Step 1: Grant *ALL Authority to GLUESYNC01

```bash
qadmcli user grant -u GLUESYNC01 -g *ALL -l GSLIBTST -n CUSTOMERS2 -t *FILE
```

**Output**:
```
Granted *ALL authority to GLUESYNC01
Object: GSLIBTST.CUSTOMERS2 (*FILE)
```

### Step 2: Verify Permissions

```bash
qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST
```

**Permission Check Results (AFTER fix)**:

```
╭───────────────── Table Permissions ─────────────────╮
│ Object              | GSLIBTST.CUSTOMERS2           │
│ Type                | *FILE                         │
│ Effective Authority | *ALL ✅                        │
│ Primary Source      | Direct User Grant             │
│ Authority Details   | - Direct User Grant: *ALL     │
│                     | - *PUBLIC: *EXCLUDE           │
╰─────────────────────────────────────────────────────╯

User has full permissions on table and journal objects.
```

### Step 3: Test Query

```bash
qadmcli sql execute -q "SELECT COUNT(*) AS ROW_COUNT FROM GSLIBTST.CUSTOMERS2"
```

**Result**:
```
   Query   
  Results  
 ROW_COUNT 
-----------
 63        
1 row(s) returned
```

✅ Query now completes instantly!

---

## Key Findings

### 1. user check-table Command Options

The `user check-table` command uses:
- `-u` / `--user` for username ✅
- `-n` / `--name` for **table name** (NOT `-t`)
- `-l` / `--library` for library name

**Correct usage**:
```bash
qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST
```

**NOT**:
```bash
qadmcli user check-table -u GLUESYNC01 -t CUSTOMERS2 -l GSLIBTST  # ❌ Wrong
```

### 2. Permission Hierarchy

AS400 permissions work as follows:
- **Direct User Grant** overrides **\*PUBLIC** authority
- **\*EXCLUDE** means NO access (even if \*PUBLIC has access)
- **\*ALL** means full access (read, write, delete, etc.)

### 3. Common Authority Levels

| Authority | Read | Update | Add | Delete | Use Case |
|-----------|------|--------|-----|--------|----------|
| `*ALL` | ✅ | ✅ | ✅ | ✅ | Full access |
| `*CHANGE` | ✅ | ✅ | ✅ | ✅ | Read + modify |
| `*USE` | ✅ | ❌ | ❌ | ❌ | Read-only |
| `*EXCLUDE` | ❌ | ❌ | ❌ | ❌ | No access |

---

## Commands Reference

### Check User Permissions

```bash
# Check table permissions (fast, doesn't query the table)
qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST

# Check user profile
qadmcli user check -u GLUESYNC01

# List all user permissions
qadmcli user permission -u GLUESYNC01
```

### Grant Permissions

```bash
# Grant full access to table
qadmcli user grant -u GLUESYNC01 -g *ALL -l GSLIBTST -n CUSTOMERS2 -t *FILE

# Grant read-only access
qadmcli user grant -u GLUESYNC01 -g *USE -l GSLIBTST -n CUSTOMERS2 -t *FILE

# Grant access to journal
qadmcli user grant -u GLUESYNC01 -g *ALL -l GSLIBTST -n GSLIBTSJRN -t *JRN

# Grant access to journal receiver
qadmcli user grant -u GLUESYNC01 -g *CHANGE -l GSLIBTST -n GSLIBT0011 -t *JRNRCV
```

### Test Queries

```bash
# Quick count test
qadmcli sql execute -q "SELECT COUNT(*) FROM GSLIBTST.CUSTOMERS2"

# Check if table exists
qadmcli sql execute -q "SELECT COUNT(*) FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA='GSLIBTST' AND TABLE_NAME='CUSTOMERS2'"

# Query with timeout (prevents hanging)
timeout 10 qadmcli sql execute -q "SELECT * FROM GSLIBTST.CUSTOMERS2 FETCH FIRST 10 ROWS ONLY"
```

---

## Troubleshooting Guide

### Query Hangs or Times Out

**Symptoms**:
- Query runs indefinitely
- No rows returned
- Eventually times out

**Possible Causes**:
1. ❌ User doesn't have permission on table
2. ❌ Table is locked by another process
3. ❌ Network connectivity issues
4. ❌ Query is too complex

**Diagnosis Steps**:

```bash
# Step 1: Check user permissions (fast)
qadmcli user check-table -u GLUESYNC01 -n TABLE_NAME -l LIBRARY

# Step 2: Check if table exists (fast)
qadmcli sql execute -q "SELECT COUNT(*) FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA='LIBRARY' AND TABLE_NAME='TABLE_NAME'"

# Step 3: Try simple query with timeout
timeout 10 qadmcli sql execute -q "SELECT COUNT(*) FROM LIBRARY.TABLE_NAME"

# Step 4: Grant permissions if needed
qadmcli user grant -u GLUESYNC01 -g *ALL -l LIBRARY -n TABLE_NAME -t *FILE
```

### Permission Denied Errors

**Symptoms**:
- SQL0404: Not authorized to object
- SQLSTATE 42501: Authorization failure

**Solution**:
```bash
# Grant appropriate authority
qadmcli user grant -u USERNAME -g *ALL -l LIBRARY -n TABLE_NAME -t *FILE
```

---

## Current Permission Status

### GLUESYNC01 on GSLIBTST Library

| Object | Type | Authority | Status |
|--------|------|-----------|--------|
| CUSTOMERS2 | *FILE | *ALL | ✅ |
| GSLIBTSJRN | *JRN | *ALL | ✅ |
| GSLIBT0011 | *JRNRCV | *CHANGE | ✅ |

### Other Tables (Previously Granted)

GLUESYNC01 also has permissions on:
- CUSTOMERS (*ALL)
- CUSTOMERS_NOPK (*ALL)
- CUSTOMERS_NONKEY (*ALL)
- ORDERS_MULTIKEY (*ALL)
- And 15+ other tables

---

## Recommendations

### For DBeaver Access

If you're using DBeaver with GLUESYNC01 to query CUSTOMERS2:

1. **Connection Settings**:
   - Username: GLUESYNC01
   - Password: (your password)
   - Database: (your AS400 database)

2. **Test Query**:
   ```sql
   SELECT COUNT(*) FROM GSLIBTST.CUSTOMERS2
   ```

3. **If Still Failing**:
   - Verify you're connected as GLUESYNC01 (not another user)
   - Check DBeaver connection settings
   - Try: `qadmcli user check-table -u GLUESYNC01 -n CUSTOMERS2 -l GSLIBTST`

### Best Practices

1. ✅ Always use `user check-table` to verify permissions before troubleshooting queries
2. ✅ Use `timeout` command to prevent hanging queries during testing
3. ✅ Grant `*ALL` for CDC/service accounts that need full access
4. ✅ Grant `*USE` for read-only reporting accounts
5. ✅ Document permission changes for audit trail

---

## Related Commands

### MSSQL Permission Check (using new credential override)

```bash
# Check if GLUESYNC01 exists in MSSQL
qadmcli mssql query -q "SELECT * FROM sys.database_principals WHERE name = 'GLUESYNC01'" -u GLUESYNC01 -p password

# Check MSSQL table permissions
qadmcli mssql query -q "
SELECT dp.name, p.permission_name, p.state_desc, OBJECT_NAME(p.major_id) AS table_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
WHERE dp.name = 'GLUESYNC01'
" -u sa -p admin_password
```

---

**Issue Resolved**: 2026-04-13 03:07  
**Resolution Time**: ~5 minutes  
**Root Cause**: Missing table permissions (*EXCLUDE)  
**Fix Applied**: Granted *ALL authority to GLUESYNC01 on CUSTOMERS2
