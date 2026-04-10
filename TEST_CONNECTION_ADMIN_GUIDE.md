# Test Connection with Admin User - Quick Guide

## Overview

The `qadmcli` test connection commands now support `-U` and `-P` options to test connections with different user credentials, particularly useful for testing admin user access.

---

## AS400 Connection Test

### Test with Default User (from config)
```bash
qadmcli connection test
```

**Output:**
```
╭──────────────── Connection Test ────────────────╮
│ Host: 161.82.146.249                            │
│ User: MYUSER                                    │
│ Status: Connected                               │
│ Version: V7R4                                   │
╰─────────────────────────────────────────────────╯
```

---

### Test with Admin User (Interactive Password)
```bash
qadmcli connection test -U QSECOFR
```

**Behavior:**
- Prompts for password (hidden input)
- Tests connection with admin credentials
- Does NOT save credentials to config

**Example:**
```bash
$ qadmcli connection test -U QSECOFR
Password for QSECOFR: ***********
Testing connection as user: QSECOFR
╭──────────────── Connection Test ────────────────╮
│ Host: 161.82.146.249                            │
│ User: QSECOFR                                   │
│ Status: Connected                               │
│ Version: V7R4                                   │
╰─────────────────────────────────────────────────╯
```

---

### Test with Admin User (Password in Command)
```bash
qadmcli connection test -U QSECOFR -P 'admin_password'
```

**⚠️ Warning:** Password visible in command history. Use interactive mode for better security.

---

### Test with JSON Output
```bash
qadmcli connection test -U QSECOFR -P 'admin_password' --json
```

**Output:**
```json
{
  "host": "161.82.146.249",
  "user": "QSECOFR",
  "connected": true,
  "server_info": {
    "version": "V7R4"
  },
  "default_library": "GSLIBTST",
  "permissions": {
    "library": {
      "object_authority": "*ALL",
      "data_read": true,
      "data_add": true,
      "data_update": true,
      "data_delete": true,
      "can_create_table": true
    }
  }
}
```

---

## MSSQL Connection Test

### Test with Default User (from config)
```bash
qadmcli mssql test
```

**Output:**
```
Testing connection to MSSQL: 192.168.13.62:1433...
╭────────── MSSQL Connection Test ──────────╮
│ Host: 192.168.13.62:1433                  │
│ User: mssql_user                          │
│ Database: GSTargetDB                      │
│ Server: MSSQLSERVER                       │
│ Version: Microsoft SQL Server 2022        │
│ Status: Connected                         │
╰───────────────────────────────────────────╯
```

---

### Test with Admin User (Interactive Password)
```bash
qadmcli mssql test -U sa
```

**Example:**
```bash
$ qadmcli mssql test -U sa
Password for sa: ***********
Testing connection as user: sa
Testing connection to MSSQL: 192.168.13.62:1433...
╭────────── MSSQL Connection Test ──────────╮
│ Host: 192.168.13.62:1433                  │
│ User: sa                                  │
│ Database: GSTargetDB                      │
│ Server: MSSQLSERVER                       │
│ Version: Microsoft SQL Server 2022        │
│ Status: Connected                         │
╰───────────────────────────────────────────╯
```

---

### Test with Admin User (Password in Command)
```bash
qadmcli mssql test -U sa -P 'your_password'
```

**⚠️ Warning:** Password visible in command history.

---

### Test with JSON Output
```bash
qadmcli mssql test -U sa -P 'your_password' --json
```

**Output:**
```json
{
  "host": "192.168.13.62",
  "port": 1433,
  "user": "sa",
  "database": "GSTargetDB",
  "server": "MSSQLSERVER",
  "version": "Microsoft SQL Server 2022 (RTM) ...",
  "status": "connected"
}
```

---

## Common Use Cases

### 1. Verify Admin Access Before Operations
```bash
# Before enabling Change Tracking on MSSQL
qadmcli mssql test -U sa -P 'admin_pass'

# Before enabling journaling on AS400
qadmcli connection test -U QSECOFR -P 'admin_pass'
```

---

### 2. Test Different User Permissions
```bash
# Test regular user
qadmcli connection test

# Test admin user
qadmcli connection test -U QSECOFR

# Compare permissions in JSON output
qadmcli connection test --json > regular_user.json
qadmcli connection test -U QSECOFR --json > admin_user.json
diff regular_user.json admin_user.json
```

---

### 3. Troubleshoot Connection Issues
```bash
# Test if admin can connect
qadmcli mssql test -U sa

# If admin works but regular user fails, check:
# - User exists in database
# - User has proper permissions
# - User has database access
```

---

### 4. Verify Credentials in Scripts
```bash
#!/bin/bash
# Test connection before running migration

if qadmcli mssql test -U "$ADMIN_USER" -P "$ADMIN_PASS" --json 2>/dev/null | \
   grep -q '"status": "connected"'; then
    echo "Admin connection OK"
    # Proceed with migration
else
    echo "Admin connection FAILED"
    exit 1
fi
```

---

## Security Best Practices

### ✅ Do's
1. **Use interactive mode** (without `-P`) when possible
   ```bash
   qadmcli connection test -U QSECOFR
   # Password prompt is hidden
   ```

2. **Use environment variables** in scripts
   ```bash
   qadmcli mssql test -U "$MSSQL_ADMIN_USER" -P "$MSSQL_ADMIN_PASSWORD"
   ```

3. **Clear bash history** if using `-P` flag
   ```bash
   history -d $(history 1)
   ```

4. **Use `.env` files** for automation
   ```bash
   source .env
   qadmcli mssql test -U "$MSSQL_ADMIN_USER" -P "$MSSQL_ADMIN_PASSWORD"
   ```

---

### ❌ Don'ts
1. **Don't hardcode passwords** in scripts
   ```bash
   # BAD
   qadmcli mssql test -U sa -P 'SuperSecret123'
   ```

2. **Don't commit passwords** to version control

3. **Don't use `-P` flag** in shared environments

4. **Don't ignore failed tests** - investigate permission issues

---

## Error Handling

### Authentication Failed
```
Connection failed: ('28000', "[28000] [Microsoft][ODBC Driver 18 for SQL Server]
[SQL Server]Login failed for user 'sa'. (18456) (SQLDriverConnect)")
```

**Solutions:**
- Verify username and password are correct
- Check if account is locked or disabled
- Verify SQL Server allows SQL authentication

---

### Permission Denied (AS400)
```
Error: [CPF7030] Object of type *FILE already being journaled.
```

**Solutions:**
- User may not have sufficient permissions
- Test with admin user: `qadmcli connection test -U QSECOFR`
- Check user authority in output JSON

---

### Connection Timeout
```
Connection failed: Connection timed out
```

**Solutions:**
- Verify host and port are correct
- Check firewall rules
- Test network connectivity: `ping <host>`

---

## Command Reference

### AS400 Connection Test
```bash
qadmcli connection test [OPTIONS]

Options:
  -U, --username TEXT  Test connection with specific username (admin user)
  -P, --password TEXT  Password for the specified username
  --json              Output in JSON format
  --help              Show this message and exit
```

---

### MSSQL Connection Test
```bash
qadmcli mssql test [OPTIONS]

Options:
  -U, --username TEXT  Test connection with specific username (admin user)
  -P, --password TEXT  Password for the specified username
  --json              Output in JSON format
  --help              Show this message and exit
```

---

## Implementation Details

### How It Works

1. **Load config** from `connection.yaml`
2. **If `-U` provided:**
   - Prompt for password (if `-P` not provided)
   - Create temporary connection config with override credentials
   - Original config remains unchanged
3. **Test connection** with provided/default credentials
4. **Display results** showing which user was tested
5. **Discard temporary config** - credentials not saved

### Security Features

- ✅ Password prompt uses `getpass` (hidden input)
- ✅ Temporary config only exists in memory
- ✅ Original config file not modified
- ✅ Credentials not logged or displayed
- ✅ Connection closed after test

---

## Related Commands

### Enable CT on Database (requires admin)
```bash
qadmcli mssql ct enable-db \
  --admin-user sa \
  --admin-password 'your_password' \
  --retention 2
```

### Enable Journaling (requires authority)
```bash
qadmcli journal enable -n CUSTOMERS -l GSLIBTST
```

### Test After Changes
```bash
# Verify connection still works
qadmcli connection test -U QSECOFR
qadmcli mssql test -U sa
```

---

## Git Commit

```
Commit: eceb66b
Message: feat(connection): add -U and -P options to test connection commands
Branch: main
Repository: https://github.com/pnandasa-aide/qadmcli.git
```

---

## Summary

The enhanced test connection commands allow you to:
- ✅ Test with different user credentials
- ✅ Verify admin access before operations
- ✅ Troubleshoot permission issues
- ✅ Compare user permissions
- ✅ Automate credential testing in scripts
- ✅ Maintain security with interactive password prompts

**Recommended Usage:**
```bash
# Interactive (most secure)
qadmcli connection test -U QSECOFR
qadmcli mssql test -U sa

# Scripted (use environment variables)
qadmcli mssql test -U "$ADMIN_USER" -P "$ADMIN_PASS"
```
