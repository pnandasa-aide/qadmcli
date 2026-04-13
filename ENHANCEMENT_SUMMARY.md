# Qadmcli Enhancement Summary

**Date**: 2026-04-13  
**Tasks**: 4 enhancement requests

---

## ✅ Task 1: Verify Mockup Command Options (COMPLETE)

### Status: Already Implemented Correctly

The mockup command already uses the correct option flags:
- `-t` / `--table` for table name ✅
- `-n` / `--number` for number of transactions ✅

### Current Implementation

```bash
qadmcli mockup generate -t CUSTOMERS -l GSLIBTST -n 50
```

**File**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/cli.py` (line 2800-2809)

```python
@mockup.command("generate")
@click.option("--table", "-t", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library/schema name")
@click.option("--number", "-n", default=1000, help="Total number of transactions")
```

**No changes needed** - implementation is already correct!

---

## ✅ Task 2: Add -u and -p Credential Override (COMPLETE)

### Status: Fully Implemented

Added `--user` / `-u` and `--password` / `-p` options to:
- `sql query` command
- `sql execute` command  
- `mssql query` command
- `mssql execute` command

### Changes Made

#### 1. Connection Model Updates

**File**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/models/connection.py`

Added `copy_with_overrides()` method to both connection classes:

```python
class AS400Connection(BaseModel):
    def copy_with_overrides(self, user: str = None, password: str = None) -> "AS400Connection":
        """Create a copy with credential overrides."""
        return AS400Connection(
            host=self.host,
            user=user or self.user,
            password=password or self.password,
            port=self.port,
            ssl=self.ssl,
            database=self.database
        )

class MSSQLConnection(BaseModel):
    def copy_with_overrides(self, username: str = None, password: str = None) -> "MSSQLConnection":
        """Create a copy with credential overrides."""
        return MSSQLConnection(
            host=self.host,
            port=self.port,
            username=username or self.username,
            password=password or self.password,
            database=self.database
        )
```

#### 2. CLI Command Updates

**File**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/cli.py`

Updated 4 commands to support credential override:

**sql query**:
```python
@sql.command("query")
@click.option("--user", "-u", default=None, help="Override username for connection")
@click.option("--password", "-p", default=None, help="Override password for connection")
def sql_query(ctx, query, target, limit, offset, output_format, user, password):
    # Apply credential overrides
    if user or password:
        mssql_config = config.mssql.copy_with_overrides(username=user, password=password)
        console.print(f"[yellow]Using credential override: user={user or '***'}[/yellow]")
```

**sql execute**: Similar implementation  
**mssql query**: Delegates to sql_query with user/password  
**mssql execute**: Delegates to sql_execute with user/password

### Usage Examples

```bash
# Query MSSQL with different user
qadmcli mssql query -q "SELECT * FROM dbo.customers2" -u GLUESYNC01 -p password123

# Execute SQL on AS400 with different credentials  
qadmcli sql execute -q "SELECT * FROM GSLIBTST.CUSTOMERS2" -t as400 -u GLUESYNC01 -p password

# Grant permissions using admin credentials
qadmcli mssql execute -q "GRANT SELECT ON dbo.customers2 TO GLUESYNC01" -u sa -p admin_password

# Check table permissions
qadmcli mssql query -q "SELECT * FROM sys.fn_my_permissions('dbo.customers2', 'OBJECT')" -u GLUESYNC01 -p password
```

### Benefits

✅ Test permissions for different users without changing config  
✅ Run administrative commands with elevated privileges  
✅ Debug permission issues by switching users  
✅ Automate multi-user testing scenarios  

---

## ✅ Task 3: AS400 Permission Grant Support (COMPLETE)

### Status: Already Fully Supported

The `qadmcli user grant` command already exists and supports all needed functionality for granting AS400 permissions.

### Current Implementation

**Command**: `qadmcli user grant`

**File**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/cli.py` (user command group)

**Options**:
```bash
-u, --user TEXT                 Username to grant permissions to  [required]
-g, --grant AUTHORITY           Authority to grant  [required]
                                Options: *ALL, *CHANGE, *USE, *EXCLUDE, *ALLOBJ, etc.
-l, --library TEXT              Library name  [required]
-n, --name TEXT                 Object name(s) (supports wildcards)
-t, --object-type TYPE          Object type: *FILE, *JRN, *JRNRCV, *LIB, *ALL
```

### Usage Examples for CUSTOMERS2

```bash
# Grant *ALL authority to GLUESYNC01 on CUSTOMERS2 table
qadmcli user grant -u GLUESYNC01 -g *ALL -l GSLIBTST -n CUSTOMERS2 -t *FILE

# Grant *CHANGE authority (read + modify)
qadmcli user grant -u GLUESYNC01 -g *CHANGE -l GSLIBTST -n CUSTOMERS2 -t *FILE

# Grant *USE authority (read-only)
qadmcli user grant -u GLUESYNC01 -g *USE -l GSLIBTST -n CUSTOMERS2 -t *FILE

# Grant authority to journal
qadmcli user grant -u GLUESYNC01 -g *ALL -l GSLIBTST -n GSLIBTSJRN -t *JRN

# Grant authority to all objects in library
qadmcli user grant -u GLUESYNC01 -g *ALL -l GSLIBTST -t *LIB
```

### Verification

```bash
# Check GLUESYNC01 permissions on CUSTOMERS2
qadmcli sql execute -q "
SELECT AUTHORIZATION_NAME, OBJECT_SCHEMA, OBJECT_NAME, OBJECT_TYPE, 
       OBJECT_AUTHORITY, DATA_READ, DATA_UPDATE, DATA_ADD, DATA_DELETE 
FROM QSYS2.OBJECT_PRIVILEGES 
WHERE AUTHORIZATION_NAME = 'GLUESYNC01' 
  AND OBJECT_SCHEMA = 'GSLIBTST' 
  AND OBJECT_NAME = 'CUSTOMERS2'
"
```

---

## ⏳ Task 4: MSSQL User Management Commands (IN PROGRESS)

### Status: Implementation Needed

Need to create MSSQL equivalents of AS400 user commands:
- `mssql user check` - Check if user exists
- `mssql user check-table` - Check user permissions on specific table
- `mssql user grant` - Grant permissions to user

### Design Plan

#### 4.1. mssql user check

```bash
qadmcli mssql user check -u GLUESYNC01
```

**Implementation**:
```python
@mssql.group()
def mssql_user():
    """MSSQL user management commands."""
    pass

@mssql_user.command("check")
@click.option("--user", "-u", required=True, help="Username to check")
@click.pass_context
def mssql_user_check(ctx, user):
    """Check if user exists and get user info."""
    query = f"""
    SELECT 
        dp.name AS UserName,
        dp.type_desc AS UserType,
        dp.default_schema_name,
        dp.create_date,
        dp.modify_date,
        CASE WHEN dp.is_disabled = 0 THEN 'No' ELSE 'Yes' END AS IsDisabled
    FROM sys.database_principals dp
    WHERE dp.name = '{user}'
    """
    # Execute and display results
```

#### 4.2. mssql user check-table

```bash
qadmcli mssql user check-table -u GLUESYNC01 -t dbo.customers2
```

**Implementation**:
```python
@mssql_user.command("check-table")
@click.option("--user", "-u", required=True, help="Username to check")
@click.option("--table", "-t", required=True, help="Table name (schema.table)")
@click.pass_context
def mssql_user_check_table(ctx, user, table):
    """Check user permissions for a specific table."""
    schema, table_name = table.split('.')
    query = f"""
    SELECT 
        dp.name AS UserName,
        p.permission_name,
        p.state_desc,
        p.class_desc,
        OBJECT_NAME(p.major_id) AS ObjectName
    FROM sys.database_permissions p
    JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
    WHERE dp.name = '{user}'
      AND p.major_id = OBJECT_ID('{table}')
    """
    # Execute and display results
```

#### 4.3. mssql user grant

```bash
qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t dbo.customers2
qadmcli mssql user grant -u GLUESYNC01 -p "SELECT,INSERT,UPDATE,DELETE" -t dbo.customers2
```

**Implementation**:
```python
@mssql_user.command("grant")
@click.option("--user", "-u", required=True, help="Username to grant permissions")
@click.option("--permission", "-p", required=True, help="Permissions (SELECT, INSERT, UPDATE, DELETE, etc.)")
@click.option("--table", "-t", required=True, help="Table name (schema.table)")
@click.option("--with-grant", is_flag=True, help="Allow user to grant these permissions to others")
@click.pass_context
def mssql_user_grant(ctx, user, permission, table, with_grant):
    """Grant permissions to user on table."""
    grant_option = " WITH GRANT OPTION" if with_grant else ""
    query = f"GRANT {permission} ON {table} TO [{user}]{grant_option}"
    
    # Execute using admin credentials (may need -U -P override)
    # Display success message
```

### Required Files

1. **New file**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/db/mssql_user.py`
   - MSSQL user management functions
   - check_user()
   - check_table_permissions()
   - grant_permissions()

2. **Update**: `/home/ubuntu/_qoder/qadmcli/src/qadmcli/cli.py`
   - Add `mssql user` command group
   - Add `mssql user check` command
   - Add `mssql user check-table` command
   - Add `mssql user grant` command

### Implementation Priority

**High Priority**:
1. `mssql user check` - Basic user existence check
2. `mssql user grant` - Grant table permissions

**Medium Priority**:
3. `mssql user check-table` - Detailed permission check

**Low Priority**:
4. `mssql user create` - Create new user
5. `mssql user delete` - Delete user
6. `mssql user list` - List all users

---

## Summary

| Task | Status | Files Changed | Implementation |
|------|--------|---------------|----------------|
| 1. Verify mockup options | ✅ COMPLETE | None (already correct) | N/A |
| 2. Add -u -p credential override | ✅ COMPLETE | connection.py, cli.py | Full implementation |
| 3. AS400 permission grant | ✅ COMPLETE | None (already exists) | N/A |
| 4. MSSQL user management | ⏳ IN PROGRESS | Need new files | Design complete, code needed |

---

## Next Steps

### Immediate (Use What's Available Now)

1. **Grant AS400 permissions to GLUESYNC01**:
   ```bash
   qadmcli user grant -u GLUESYNC01 -g *ALL -l GSLIBTST -n CUSTOMERS2 -t *FILE
   qadmcli user grant -u GLUESYNC01 -g *ALL -l GSLIBTST -n GSLIBTSJRN -t *JRN
   ```

2. **Create GLUESYNC01 on MSSQL** (using existing mssql execute):
   ```bash
   qadmcli mssql execute -q "CREATE LOGIN GLUESYNC01 WITH PASSWORD = 'password123'" -u sa -p admin_pass
   qadmcli mssql execute -q "USE GSTargetDB; CREATE USER GLUESYNC01 FOR LOGIN GLUESYNC01" -u sa -p admin_pass
   qadmcli mssql execute -q "GRANT SELECT ON dbo.customers2 TO GLUESYNC01" -u sa -p admin_pass
   ```

3. **Test with credential override**:
   ```bash
   qadmcli mssql query -q "SELECT COUNT(*) FROM dbo.customers2" -u GLUESYNC01 -p password123
   ```

### Future Enhancement

Complete Task 4 implementation for proper MSSQL user management commands with:
- Better error handling
- Permission validation
- Bulk operations
- Permission reporting

---

## Testing Recommendations

### Test Credential Override

```bash
# Test 1: Query with config credentials (default)
qadmcli mssql query -q "SELECT COUNT(*) FROM dbo.customers"

# Test 2: Query with override credentials
qadmcli mssql query -q "SELECT COUNT(*) FROM dbo.customers" -u GLUESYNC01 -p password

# Test 3: Execute admin command with override
qadmcli mssql execute -q "GRANT SELECT ON dbo.customers TO GLUESYNC01" -u sa -p admin_password

# Test 4: Verify grant worked
qadmcli mssql query -q "SELECT * FROM dbo.customers" -u GLUESYNC01 -p password
```

### Test AS400 Permissions

```bash
# Grant permissions
qadmcli user grant -u GLUESYNC01 -g *ALL -l GSLIBTST -n CUSTOMERS2 -t *FILE

# Verify
qadmcli sql execute -q "
SELECT OBJECT_NAME, OBJECT_AUTHORITY, DATA_READ, DATA_UPDATE 
FROM QSYS2.OBJECT_PRIVILEGES 
WHERE AUTHORIZATION_NAME = 'GLUESYNC01' AND OBJECT_NAME = 'CUSTOMERS2'
"
```

---

*Implementation completed on 2026-04-13*
