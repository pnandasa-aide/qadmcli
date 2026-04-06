# QADM CLI Helper Scripts

## Quick Start

Use these helper scripts to run qadmcli without typing long podman commands.

## Windows (PowerShell)

```powershell
# Show help
.\qadmcli.ps1 --help

# Test connections
.\qadmcli.ps1 connection test

# List tables on AS400
.\qadmcli.ps1 table list -l GSLIBTST

# Convert schema (output to console)
.\qadmcli.ps1 -- table convert -s config/schema/subscriber.yaml --source-db DB2 --target-db MSSQL

# Convert schema (save to file) - NOTE: use -- before arguments
.\qadmcli.ps1 -- table convert -s config/schema/subscriber.yaml --source-db DB2 --target-db MSSQL -o output.yaml

# Create table on MSSQL (dry run)
.\qadmcli.ps1 -- table create-mssql -n subscribers -s config/schema/subscriber_mssql.yaml -d GSTargetDB --dry-run

# Create table on MSSQL (execute)
.\qadmcli.ps1 -- table create-mssql -n subscribers -s config/schema/subscriber_mssql.yaml -d GSTargetDB
```

## Linux/macOS (Bash)

```bash
# Make executable first
chmod +x qadmcli.sh

# Show help
./qadmcli.sh --help

# Test connections
./qadmcli.sh connection test

# List tables on AS400
./qadmcli.sh table list -l GSLIBTST

# Convert schema
./qadmcli.sh table convert -s config/schema/subscriber.yaml --source-db DB2 --target-db MSSQL

# Convert and save
./qadmcli.sh table convert -s config/schema/subscriber.yaml --source-db DB2 --target-db MSSQL -o output.yaml

# Create table on MSSQL
./qadmcli.sh table create-mssql -n subscribers -s config/schema/subscriber_mssql.yaml -d GSTargetDB --dry-run
```

## Important Notes

### Windows PowerShell - Using `--`

When passing arguments that start with `-` (like `-o`, `-s`, `-n`), PowerShell may interpret them as PowerShell parameters. To avoid this, use `--` before the qadmcli arguments:

```powershell
# ❌ This might fail
.\qadmcli.ps1 table convert -s schema.yaml -o output.yaml

# ✅ This works
.\qadmcli.ps1 -- table convert -s schema.yaml -o output.yaml
```

### First Run - Image Building

On first run, the script will automatically build the container image. This takes a few minutes. Subsequent runs will use the cached image.

To force rebuild:
```bash
podman rmi qadmcli
```

### Environment Variables

The scripts automatically load environment variables from `.env` file in the project root. Make sure your `.env` file contains:

```env
AS400_USER=your_as400_user
AS400_PASSWORD=your_as400_password
MSSQL_USER=your_mssql_user
MSSQL_PASSWORD=your_mssql_password
```

## Common Commands

### Schema Operations

```powershell
# Convert DB2 schema to MSSQL format
.\qadmcli.ps1 -- table convert -s config/schema/subscriber.yaml --source-db DB2 --target-db MSSQL -o subscriber_mssql.yaml

# Create table on AS400
.\qadmcli.ps1 table create -n SUBSCRIBER -l GSLIBTST -s config/schema/subscriber.yaml

# Create table on MSSQL
.\qadmcli.ps1 -- table create-mssql -n subscribers -s config/schema/subscriber_mssql.yaml -d GSTargetDB

# Compare schemas between DB2 and MSSQL
.\qadmcli.ps1 -- table compare-schemas --db2-table GSLIBTST.SUBSCRIBER --mssql-table dbo.subscribers
```

### Mockup Data

```powershell
# Generate mock data on AS400
.\qadmcli.ps1 -- mockup generate -n SUBSCRIBER -l GSLIBTST -t 100 --dry-run

# Generate with schema hints
.\qadmcli.ps1 -- mockup generate -n ORDERTRANX -l GSLIBTST -s config/schema/ordertranx.yaml -t 100
```

### Table Management

```powershell
# Check table exists
.\qadmcli.ps1 table check -n SUBSCRIBER -l GSLIBTST

# Reverse engineer table to YAML
.\qadmcli.ps1 table reverse -n SUBSCRIBER -l GSLIBTST -o reversed.yaml

# Drop table
.\qadmcli.ps1 table drop -n SUBSCRIBER -l GSLIBTST

# Empty table
.\qadmcli.ps1 table empty -n SUBSCRIBER -l GSLIBTST
```

## MSSQL Database Setup Guide

### Step 1: Create Database

```sql
-- Create the target database
CREATE DATABASE GSTargetDB;
GO
```

### Step 2: Create Login

```sql
-- Create SQL Server login (use strong password in production)
-- Store password in .env file as MSSQL_PASSWORD
CREATE LOGIN gstgdblogin WITH PASSWORD = '${MSSQL_PASSWORD}';
GO
```

> **Security Note:** Never hardcode passwords in SQL scripts. Use the `.env` file to store credentials securely.

### Step 3: Create User and Assign Permissions

```sql
-- Switch to the target database
USE GSTargetDB;
GO

-- Create database user mapped to the login
CREATE USER gstgdbuser FOR LOGIN gstgdblogin;
GO
```

### Step 4: Grant Roles

```sql
-- Add user to fixed database roles
ALTER ROLE db_owner ADD MEMBER gstgdbuser;
GO

-- Alternative: Granular permissions
-- DDL administration (CREATE/ALTER/DROP tables)
ALTER ROLE db_ddladmin ADD MEMBER gstgdbuser;
GO

-- Data read/write permissions
ALTER ROLE db_datawriter ADD MEMBER gstgdbuser;
GO
ALTER ROLE db_datareader ADD MEMBER gstgdbuser;
GO
```

### Step 5: Grant Schema Permissions

```sql
-- Grant schema-level permissions for DDL operations
GRANT ALTER ON SCHEMA::dbo TO gstgdbuser;
GO

-- Optional: Explicit schema permissions
-- GRANT CREATE TABLE TO gstgdbuser;
-- GRANT DROP ON SCHEMA::dbo TO gstgdbuser;
-- GRANT INSERT, UPDATE, DELETE ON SCHEMA::dbo TO gstgdbuser;
```

### Verify Setup

```sql
-- Check user permissions
USE GSTargetDB;
GO

SELECT 
    dp.name AS UserName,
    dr.name AS RoleName
FROM sys.database_role_members drm
JOIN sys.database_principals dp ON drm.member_principal_id = dp.principal_id
JOIN sys.database_principals dr ON drm.role_principal_id = dr.principal_id
WHERE dp.name = 'gstgdbuser';
```

## AS400 DB2 for i Setup Guide

### Step 1: Create Library (Schema)

**Using TN5250 (5250 Emulator):**
```
===> CRTLIB LIB(GSLIBTST) TEXT('Test Library for Data Replication')
```

**Using qadmcli:**
```powershell
# Note: qadmcli does not support library creation directly
# Use CRTLIB command via TN5250 or ODBC
```

### Step 2: Create User Profile

**Using TN5250:**
```
===> CRTUSRPRF USRPRF(GSLIBUSER) PASSWORD(*NONE) 
     USRCLS(*PGMR) INLMNU(*SIGNOFF) 
     CURLIB(GSLIBTST) TEXT('Data Replication User')
```

**Set Password:**
```
===> CHGUSRPRF USRPRF(GSLIBUSER) PASSWORD(YourPassword)
```

**Using qadmcli (Supported):**
```powershell
# Create user
.\qadmcli.ps1 user create -u GSLIBUSER -p YourPassword

# Or with additional options
.\qadmcli.ps1 user create -u GSLIBUSER -p YourPassword --user-class *PGMR
```

### Step 3: Grant Library Permissions

**Using TN5250:**
```
===> GRTOBJAUT OBJ(GSLIBTST) OBJTYPE(*LIB) USER(GSLIBUSER) 
     AUT(*ALL)
```

**Using qadmcli (Supported):**
```powershell
# Grant authority to library
.\qadmcli.ps1 user grant -u GSLIBUSER -l GSLIBTST -a *ALL

# Or specific authorities
.\qadmcli.ps1 user grant -u GSLIBUSER -l GSLIBTST -a "*USE *ADD *DLT *UPD"
```

### Step 4: Grant Object Permissions

**Using TN5250:**
```
# Grant permissions on all objects in library
===> GRTOBJAUT OBJ(GSLIBTST/*ALL) OBJTYPE(*ALL) 
     USER(GSLIBUSER) AUT(*ALL)

# Grant specific permissions on tables
===> GRTOBJAUT OBJ(GSLIBTST/SUBSCRIBER) OBJTYPE(*FILE) 
     USER(GSLIBUSER) AUT(*OBJOPR *READ *ADD *UPD *DLT)
```

**Using qadmcli (Supported):**
```powershell
# Check user permissions
.\qadmcli.ps1 user permission -u GSLIBUSER

# Check specific library permissions
.\qadmcli.ps1 user check -u GSLIBUSER -l GSLIBTST
```

### Step 5: Configure Journal (Optional but Recommended)

**Prerequisites:** Journal and journal receiver must be created before enabling journaling on tables.

**Using TN5250:**
```
# Create journal receiver
===> CRTJRNRCV JRNRCV(GSLIBTST/QSQJRN0001) 
     TEXT('Journal receiver for GSLIBTST')

# Create journal
===> CRTJRN JRN(GSLIBTST/QSQJRN) JRNRCV(GSLIBTST/QSQJRN0001)
     TEXT('Journal for GSLIBTST library')

# Start journaling for table
===> STRJRNPF FILE(GSLIBTST/SUBSCRIBER) 
     JRN(GSLIBTST/QSQJRN) IMAGES(*BOTH)
```

**Using qadmcli (Supported):**
```powershell
# Create journal receiver
.\qadmcli.ps1 -- journal create-receiver -n QSQJRN0001 -l GSLIBTST

# Create journal and attach to receiver
.\qadmcli.ps1 -- journal create -n QSQJRN -l GSLIBTST -r QSQJRN0001

# Or with receiver in different library
.\qadmcli.ps1 -- journal create -n QSQJRN -l GSLIBTST -r QSQJRN0001 -rl QJRNLIB

# Check journal status
.\qadmcli.ps1 journal check -n SUBSCRIBER -l GSLIBTST

# Enable journaling (journal must already exist)
.\qadmcli.ps1 journal enable -n SUBSCRIBER -l GSLIBTST

# Enable with specific journal
.\qadmcli.ps1 journal enable -n SUBSCRIBER -l GSLIBTST -j QJRNLIB -jn QSQJRN

# Get journal entries
.\qadmcli.ps1 journal entries -n SUBSCRIBER -l GSLIBTST -e 100
```

> **Note:** The `journal enable` command does NOT auto-create journals. You must explicitly create the journal receiver and journal first using `journal create-receiver` and `journal create` commands, or via TN5250.

### Cross-Library Journal Support

**Question:** Can the journal be in a different library than the table?

**Answer:** **YES!** AS400 supports cross-library journaling. The journal and journal receiver can reside in a different library than the tables being journaled.

**Example Configuration:**
```
Library Structure:
- GSLIBTST     (Table library - contains SUBSCRIBER, ORDERTRANX tables)
- QJRNLIB      (Journal library - contains QSQJRN journal and receivers)
```

**Setup:**
```powershell
# Create journal receiver in QJRNLIB
.\qadmcli.ps1 -- journal create-receiver -n QSQJRN0001 -l QJRNLIB

# Create journal in QJRNLIB
.\qadmcli.ps1 -- journal create -n QSQJRN -l QJRNLIB -r QSQJRN0001

# Enable journaling for table in GSLIBTST using journal in QJRNLIB
.\qadmcli.ps1 journal enable -n SUBSCRIBER -l GSLIBTST -j QJRNLIB -jn QSQJRN

# Retrieve journal entries (automatically finds journal across libraries)
.\qadmcli.ps1 journal entries -n SUBSCRIBER -l GSLIBTST -e 100
```

**How it works:**
- The `journal check` command reads the table's journal association from system catalogs
- The `journal entries` command automatically locates the correct journal regardless of which library it's in
- Journal entries are filtered by the table's system name (OBJECT column in DISPLAY_JOURNAL)

**Benefits:**
- Centralized journal management across multiple table libraries
- Separate backup/recovery strategies for journals vs tables
- Simplified administration for multi-library applications

### Step 6: Verify User Setup

**Using TN5250:**
```
# Display user profile
===> DSPUSRPRF USRPRF(GSLIBUSER)

# Display object authority
===> DSPOBJAUT OBJ(GSLIBTST) OBJTYPE(*LIB) USER(GSLIBUSER)
```

**Using qadmcli (Supported):**
```powershell
# Check user exists and status
.\qadmcli.ps1 user check -u GSLIBUSER

# List all user permissions
.\qadmcli.ps1 user permission -u GSLIBUSER
```

### AS400 User Management Quick Reference

| Task | TN5250 Command | qadmcli Command |
|------|---------------|-----------------|
| Create User | `CRTUSRPRF` | `user create -u <user> -p <pass>` |
| Delete User | `DLTUSRPRF` | `user delete -u <user>` |
| Change Password | `CHGUSRPRF` | `user password -u <user> -p <pass>` |
| Grant Authority | `GRTOBJAUT` | `user grant -u <user> -l <lib> -a <aut>` |
| Check User | `DSPUSRPRF` | `user check -u <user>` |
| List Permissions | `DSPOBJAUT` | `user permission -u <user>` |
| Create Library | `CRTLIB` | Not Supported |
| Delete Library | `DLTLIB` | Not Supported |

### AS400 Journal Management Quick Reference

| Task | TN5250 Command | qadmcli Command |
|------|---------------|-----------------|
| Create Journal Receiver | `CRTJRNRCV` | `journal create-receiver -n <name> -l <lib>` |
| Create Journal | `CRTJRN` | `journal create -n <name> -l <lib> -r <rcv>` |
| Enable Journaling | `STRJRNPF` | `journal enable -n <table> -l <lib> [-j <jrnlib>]` |
| Disable Journaling | `ENDJRNPF` | Not Supported |
| Check Journal Status | `DSPFD` | `journal check -n <table> -l <lib>` |
| Get Journal Entries | `DSPJRN` | `journal entries -n <table> -l <lib> -e <count>` |
| Get Journal Info | `DSPJRN` | `journal info -n <table> -l <lib>` |

### Connection Configuration

After setup, configure `config/connection.yaml`:

```yaml
as400:
  host: "161.82.146.249"
  user: "${AS400_USER}"      # Set to GSLIBUSER
  password: "${AS400_PASSWORD}"  # Set to your password
  port: 8471
  ssl: false
  database: "GSLIBTST"

defaults:
  library: "GSLIBTST"
  journal_library: "QSYS2"
```

And `.env` file:
```env
AS400_USER=GSLIBUSER
AS400_PASSWORD=YourPassword
```

## Troubleshooting

### "Cannot connect to Podman"

Start the Podman machine:
```powershell
podman machine start
```

### "Image build failed"

Check the Containerfile syntax and try rebuilding:
```bash
podman rmi qadmcli
.\qadmcli.ps1 connection test
```

### "Permission denied" (Linux)

Make sure the script is executable:
```bash
chmod +x qadmcli.sh
```
