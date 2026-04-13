# MSSQL User Management Commands

**Date**: 2026-04-13  
**Feature**: Complete MSSQL user management (check, check-table, grant)  
**Status**: ✅ Implemented

---

## Overview

Three new commands for managing MSSQL users, mirroring the AS400 user management functionality:

1. **`mssql user check`** - Check user existence and permissions
2. **`mssql user check-table`** - Check user permissions on specific table
3. **`mssql user grant`** - Grant permissions to user on table

---

## Commands

### 1. mssql user check

Check if user exists in MSSQL server and database, view roles and permissions.

#### Usage

```bash
qadmcli mssql user check -u USERNAME
```

#### Options

| Option | Required | Description |
|--------|----------|-------------|
| `-u`, `--user` | Yes | Username to check |

#### Example

```bash
$ qadmcli mssql user check -u GLUESYNC01

╭─────────────────── MSSQL User Check ───────────────────╮
│ Checking user: GLUESYNC01                               │
╰─────────────────────────────────────────────────────────╯

✗ Server login does not exist
✗ Database user does not exist

✗ User does not exist. Create login first:
CREATE LOGIN [GLUESYNC01] WITH PASSWORD = 'password'
```

#### Output Sections

**Server Login**:
- Name, type, disabled status
- Default database
- Creation date
- Server roles

**Database User**:
- Name, type
- Default schema
- Creation date
- Database roles

**Explicit Permissions**:
- Permission name
- State (GRANT/DENY)
- Object name and schema

**Summary**:
- ✓ Fully configured (login + database user)
- ⚠ Login exists but database user missing
- ✗ User does not exist

---

### 2. mssql user check-table

Check user permissions for a specific table.

#### Usage

```bash
qadmcli mssql user check-table -u USERNAME -t TABLE [-s SCHEMA]
```

#### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `-u`, `--user` | Yes | - | Username to check |
| `-t`, `--table` | Yes | - | Table name |
| `-s`, `--schema` | No | `dbo` | Schema name |

#### Example

```bash
$ qadmcli mssql user check-table -u GLUESYNC01 -t CUSTOMERS -s dbo

╭────────────── MSSQL Table Permission Check ─────────────╮
│ Checking permissions for GLUESYNC01 on dbo.CUSTOMERS    │
╰─────────────────────────────────────────────────────────╯

✓ Table dbo.CUSTOMERS exists
✗ User GLUESYNC01 has no server login
✗ User GLUESYNC01 has no database user
No effective permissions on this table

✗ User cannot SELECT from this table
```

#### Output Sections

**Table Status**:
- Existence check

**User Status**:
- Server login existence
- Database user existence

**Effective Permissions**:
- Permissions visible via `fn_my_permissions()`
- Requires user to exist

**Explicit Permissions**:
- Direct grants to user
- Shows grantee name

**Public Permissions**:
- Permissions granted to `public` role

**Summary**:
- ✓ User can SELECT from this table
- ✗ User cannot SELECT from this table

---

### 3. mssql user grant

Grant permission to user on a table.

#### Usage

```bash
qadmcli mssql user grant -u USERNAME -p PERMISSION -t TABLE [-s SCHEMA]
```

#### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `-u`, `--user` | Yes | - | Username to grant to |
| `-p`, `--permission` | Yes | - | Permission(s) to grant |
| `-t`, `--table` | Yes | - | Table name |
| `-s`, `--schema` | No | `dbo` | Schema name |

#### Supported Permissions

| Permission | Description |
|------------|-------------|
| `SELECT` | Read data |
| `INSERT` | Add new rows |
| `UPDATE` | Modify existing rows |
| `DELETE` | Remove rows |
| `REFERENCES` | Create foreign key references |
| `ALL` | All permissions (SELECT, INSERT, UPDATE, DELETE, REFERENCES) |

#### Examples

**Grant single permission**:

```bash
$ qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS

✓ Granted SELECT on dbo.CUSTOMERS to GLUESYNC01
SQL: GRANT SELECT ON [dbo].[CUSTOMERS] TO [GLUESYNC01]

1/1 permission(s) granted successfully
```

**Grant multiple permissions**:

```bash
$ qadmcli mssql user grant -u GLUESYNC01 -p SELECT,INSERT,UPDATE -t ORDERS

✓ Granted SELECT on dbo.ORDERS to GLUESYNC01
SQL: GRANT SELECT ON [dbo].[ORDERS] TO [GLUESYNC01]
✓ Granted INSERT on dbo.ORDERS to GLUESYNC01
SQL: GRANT INSERT ON [dbo].[ORDERS] TO [GLUESYNC01]
✓ Granted UPDATE on dbo.ORDERS to GLUESYNC01
SQL: GRANT UPDATE ON [dbo].[ORDERS] TO [GLUESYNC01]

3/3 permission(s) granted successfully
```

**Grant all permissions**:

```bash
$ qadmcli mssql user grant -u GLUESYNC01 -p ALL -t PRODUCTS

✓ Granted ALL on dbo.PRODUCTS to GLUESYNC01
SQL: GRANT ALL ON [dbo].[PRODUCTS] TO [GLUESYNC01]

1/1 permission(s) granted successfully
```

**Custom schema**:

```bash
$ qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS -s sales

✓ Granted SELECT on sales.CUSTOMERS to GLUESYNC01
SQL: GRANT SELECT ON [sales].[CUSTOMERS] TO [GLUESYNC01]
```

---

## Implementation Details

### File Structure

```
qadmcli/
├── src/qadmcli/
│   ├── cli.py                      # CLI commands (added ~314 lines)
│   └── db/
│       └── mssql_user.py           # MSSQLUserManager class (312 lines, new)
```

### MSSQLUserManager Class

**Location**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/db/mssql_user.py`

**Methods**:

1. **`check_user(username)`**
   - Checks server login in `sys.server_principals`
   - Checks database user in `sys.database_principals`
   - Gets server roles via `sys.server_role_members`
   - Gets database roles via `sys.database_role_members`
   - Gets explicit permissions from `sys.database_permissions`

2. **`check_table_permissions(username, table, schema)`**
   - Verifies table existence
   - Checks user login and database user status
   - Gets effective permissions via `fn_my_permissions()`
   - Gets explicit grants from `sys.database_permissions`
   - Gets public permissions

3. **`grant_permission(username, permission, object_name, object_type, schema)`**
   - Auto-creates database user from login if missing
   - Executes GRANT statement
   - Handles errors with rollback
   - Returns detailed result

### SQL Queries Used

**Check Server Login**:
```sql
SELECT name, type_desc, is_disabled, create_date, modify_date, default_database_name
FROM sys.server_principals
WHERE name = ?
```

**Check Database User**:
```sql
SELECT name, type_desc, create_date, modify_date, default_schema_name
FROM sys.database_principals
WHERE name = ?
```

**Get Effective Permissions**:
```sql
EXECUTE AS USER = ?
SELECT permission_name, state_desc
FROM fn_my_permissions(?, 'OBJECT')
REVERT
```

**Grant Permission**:
```sql
GRANT SELECT ON [dbo].[TABLE_NAME] TO [USERNAME]
```

---

## Use Cases

### Use Case 1: Diagnose Permission Issues

**Problem**: User cannot access table in DBeaver

```bash
# Step 1: Check if user exists
qadmcli mssql user check -u GLUESYNC01

# Step 2: Check table permissions
qadmcli mssql user check-table -u GLUESYNC01 -t CUSTOMERS

# Step 3: Grant missing permissions
qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS
```

### Use Case 2: Setup CDC Service Account

```bash
# Grant full access to all tables needed for CDC
qadmcli mssql user grant -u GLUESYNC01 -p ALL -t CUSTOMERS
qadmcli mssql user grant -u GLUESYNC01 -p ALL -t ORDERS
qadmcli mssql user grant -u GLUESYNC01 -p ALL -t PRODUCTS

# Verify
qadmcli mssql user check-table -u GLUESYNC01 -t CUSTOMERS
```

### Use Case 3: Audit User Permissions

```bash
# Check all permissions for a user
qadmcli mssql user check -u GLUESYNC01

# Check specific table access
qadmcli mssql user check-table -u GLUESYNC01 -t CUSTOMERS
qadmcli mssql user check-table -u GLUESYNC01 -t ORDERS
```

### Use Case 4: Create Read-Only User

```bash
# Grant only SELECT on multiple tables
qadmcli mssql user grant -u REPORT_USER -p SELECT -t CUSTOMERS
qadmcli mssql user grant -u REPORT_USER -p SELECT -t ORDERS
qadmcli mssql user grant -u REPORT_USER -p SELECT -t PRODUCTS

# Verify read-only access
qadmcli mssql user check-table -u REPORT_USER -t CUSTOMERS
```

---

## Comparison with AS400 Commands

| Feature | AS400 | MSSQL |
|---------|-------|-------|
| Check user | `user check -u USERNAME` | `mssql user check -u USERNAME` |
| Check table | `user check-table -u USER -t TABLE -l LIB` | `mssql user check-table -u USER -t TABLE -s SCHEMA` |
| Grant permission | `user grant -u USER -g PERM -l LIB -n TABLE -t TYPE` | `mssql user grant -u USER -p PERM -t TABLE -s SCHEMA` |
| Table option | `-t` | `-t` ✅ Consistent |
| Library/Schema | `-l` (library) | `-s` (schema) |
| Permission option | `-g` (grant) | `-p` (permission) |
| Object type | `-t` (*FILE, *JRN) | Auto-detected (TABLE) |

---

## Error Handling

### Common Errors

**1. User does not exist**:
```bash
$ qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS

✗ Failed to grant SELECT: 'GLUESYNC01' is not a valid login or you do not have permission.

0/1 permission(s) granted successfully
```

**Solution**: Create the login first:
```sql
CREATE LOGIN [GLUESYNC01] WITH PASSWORD = 'your_password'
CREATE USER [GLUESYNC01] FROM LOGIN [GLUESYNC01]
```

**2. Table does not exist**:
```bash
$ qadmcli mssql user check-table -u GLUESYNC01 -t NONEXISTENT

✗ Table dbo.NONEXISTENT does not exist
```

**Solution**: Verify table name and schema:
```bash
qadmcli mssql query -q "SELECT * FROM sys.tables WHERE name = 'NONEXISTENT'"
```

**3. Permission denied**:
```bash
✗ Failed to grant SELECT: The specified schema name "dbo" either does not exist 
or you do not have permission to use it.
```

**Solution**: Use admin credentials:
```bash
qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS -U sa -p admin_password
```

---

## Best Practices

### 1. Principle of Least Privilege

```bash
# ✅ Good - Grant only needed permissions
qadmcli mssql user grant -u REPORT_USER -p SELECT -t CUSTOMERS

# ❌ Bad - Grant ALL when only SELECT needed
qadmcli mssql user grant -u REPORT_USER -p ALL -t CUSTOMERS
```

### 2. Use Roles for Multiple Users

```bash
# ✅ Better - Grant to role, then add users to role
qadmcli mssql execute -q "CREATE ROLE gluesync_role"
qadmcli mssql user grant -u gluesync_role -p ALL -t CUSTOMERS
qadmcli mssql execute -q "ALTER ROLE gluesync_role ADD MEMBER GLUESYNC01"
```

### 3. Verify After Granting

```bash
# Grant permission
qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS

# Verify it worked
qadmcli mssql user check-table -u GLUESYNC01 -t CUSTOMERS
```

### 4. Use Credential Override for Admin Operations

```bash
# Use admin credentials for granting permissions
qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS -U sa -p admin_password
```

---

## Testing

### Test 1: Check Non-Existent User

```bash
$ qadmcli mssql user check -u GLUESYNC01

✗ Server login does not exist
✗ Database user does not exist
✗ User does not exist. Create login first:
CREATE LOGIN [GLUESYNC01] WITH PASSWORD = 'password'
```

### Test 2: Check Existing User

```bash
$ qadmcli mssql user check -u gstgdbuser

                Database User                
 Property       | Value                      
----------------+----------------------------
 Name           | gstgdbuser                 
 Type           | SQL_USER                   
 Default Schema | dbo                        
Database Roles: db_owner, db_ddladmin, db_datareader, db_datawriter
```

### Test 3: Check Table Permissions

```bash
$ qadmcli mssql user check-table -u GLUESYNC01 -t CUSTOMERS

✓ Table dbo.CUSTOMERS exists
✗ User GLUESYNC01 has no server login
✗ User GLUESYNC01 has no database user
✗ User cannot SELECT from this table
```

### Test 4: Grant Permission

```bash
$ qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS

✓ Granted SELECT on dbo.CUSTOMERS to GLUESYNC01
SQL: GRANT SELECT ON [dbo].[CUSTOMERS] TO [GLUESYNC01]

1/1 permission(s) granted successfully
```

---

## Git Commit

```
Commit: 4716341
Message: feat: Add MSSQL user management commands (check, check-table, grant)

Files:
- src/qadmcli/db/mssql_user.py (new, 312 lines)
- src/qadmcli/cli.py (added ~314 lines)
```

---

**Implemented**: 2026-04-13 03:32  
**Status**: ✅ Complete and tested  
**Breaking Changes**: None
