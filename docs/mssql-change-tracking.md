# MSSQL Change Tracking (CT) vs Change Data Capture (CDC)

## Overview

SQL Server provides two mechanisms for tracking data changes:

| Feature | Change Tracking (CT) | Change Data Capture (CDC) |
|---------|---------------------|---------------------------|
| **Purpose** | Lightweight change detection | Comprehensive audit logging |
| **Performance Impact** | Minimal | Moderate to High |
| **Storage** | Small (metadata only) | Large (full change history) |
| **Data Captured** | What changed (PK + operation) | Full before/after values |
| **Use Case** | Sync, cache invalidation | Audit trails, compliance |
| **SQL Server Edition** | All editions | Enterprise/Standard+ |

## Change Tracking (CT) Deep Dive

### How CT Works

1. **Database Level**: Must be enabled first on the database
   - Stores minimal metadata about changes
   - Maintains a version counter for the entire database
   - Automatically cleans up old data based on retention policy

2. **Table Level**: Enabled on individual tables
   - Tracks only Primary Key values of changed rows
   - Records operation type (I=Insert, U=Update, D=Delete)
   - Optionally tracks which columns were updated

### CT Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SQL Server Database                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌──────────────────────────────────┐  │
│  │  sys.change_    │  │         Your Tables              │  │
│  │  tracking_      │  │  ┌──────────┐    ┌──────────┐   │  │
│  │  databases      │  │  │ CUSTOMERS│    │  ORDERS  │   │  │
│  │                 │  │  │  (CT)    │    │  (CT)    │   │  │
│  │  • version      │  │  └──────────┘    └──────────┘   │  │
│  │  • retention    │  │                                  │  │
│  │  • cleanup      │  │  CT tracks:                      │  │
│  └─────────────────┘  │  • Primary Key values            │  │
│                       │  • Operation (I/U/D)             │  │
│  ┌─────────────────┐  │  • Version number                │  │
│  │  CHANGETABLE()  │  │  • Column changes (optional)     │  │
│  │  function       │  │                                  │  │
│  │                 │  │  Does NOT track:                 │  │
│  │  Query changes  │  │  • Full row data                 │  │
│  │  by version     │  │  • Before/after values           │  │
│  └─────────────────┘  │                                  │  │
└─────────────────────────────────────────────────────────────┘
```

### CT Workflow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   INSERT     │────▶│  CT Version  │────▶│  CHANGETABLE │
│   UPDATE     │     │  Incremented │     │  Records PK  │
│   DELETE     │     │              │     │  + Operation │
└──────────────┘     └──────────────┘     └──────────────┘
                                                  │
                                                  ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Application │◀────│  Query with  │◀────│  Get Changes │
│  Syncs Data  │     │  Version     │     │  Since Last  │
│              │     │              │     │  Sync        │
└──────────────┘     └──────────────┘     └──────────────┘
```

## Prerequisites and Hierarchy

### Enable Order (Important!)

**You MUST enable CT in this order:**

1. **Database Level First** (one-time setup)
   ```sql
   ALTER DATABASE [YourDB] SET CHANGE_TRACKING = ON
   (CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON)
   ```

2. **Table Level Second** (per table)
   ```sql
   ALTER TABLE [dbo].[YourTable] ENABLE CHANGE_TRACKING
   WITH (TRACK_COLUMNS_UPDATED = ON)
   ```

### Table Requirements

- **Primary Key is MANDATORY**: Tables must have a primary key
- **No computed columns**: CT doesn't track computed columns
- **Permissions**: ALTER permission on the table

### Disable Order (Reverse!)

**Disable in reverse order:**

1. Disable CT on all tables first
2. Then disable CT on database

```sql
-- Step 1: Disable on tables
ALTER TABLE [dbo].[YourTable] DISABLE CHANGE_TRACKING

-- Step 2: Disable on database (only after all tables)
ALTER DATABASE [YourDB] SET CHANGE_TRACKING = OFF
```

## CT Data Retention

CT automatically cleans up old change data based on the retention period:

```sql
-- Set retention to 7 days
ALTER DATABASE [YourDB] SET CHANGE_TRACKING = ON
(CHANGE_RETENTION = 7 DAYS, AUTO_CLEANUP = ON)
```

**Important**: If you don't query changes within the retention period, you'll get an error:
```
The minimum valid version is higher than the requested version.
```

## Querying Changes

### Using CHANGETABLE

```sql
-- Get all changes since version 0
SELECT 
    c.SYS_CHANGE_VERSION,
    c.SYS_CHANGE_OPERATION,
    c.SYS_CHANGE_COLUMNS,
    c.CUST_ID  -- Primary Key column(s)
FROM CHANGETABLE(CHANGES dbo.CUSTOMERS, 0) c
ORDER BY c.SYS_CHANGE_VERSION

-- Get changes since specific version
FROM CHANGETABLE(CHANGES dbo.CUSTOMERS, 12345) c
```

### Operation Types

| Code | Meaning | Typical Action |
|------|---------|----------------|
| I | Insert | Add new record to target |
| U | Update | Update existing record in target |
| D | Delete | Remove record from target |

## CT vs CDC: When to Use Which?

### Use CT When:
- ✅ You need lightweight change detection
- ✅ Building data synchronization
- ✅ Cache invalidation
- ✅ All SQL Server editions
- ✅ Minimal performance impact

### Use CDC When:
- ✅ Full audit trail required
- ✅ Compliance/regulatory requirements
- ✅ Need before/after values
- ✅ Historical data analysis
- ✅ Enterprise/Standard edition available

## Performance Considerations

### CT Overhead
- **Storage**: ~10-20 bytes per changed row
- **CPU**: Minimal (just PK + version tracking)
- **I/O**: Small increase in transaction log

### CDC Overhead
- **Storage**: Full row data stored twice (before + after)
- **CPU**: Higher (capture job runs asynchronously)
- **I/O**: Significant increase in transaction log and data files

## qadmcli MSSQL Commands

### Test Connection
```bash
# Test MSSQL connection
qadmcli mssql test

# JSON output
qadmcli --json mssql test
```

### Execute Queries
```bash
# Query MSSQL directly (alternative to sql query --target mssql)
qadmcli mssql query -q "SELECT * FROM dbo.CUSTOMERS"
qadmcli mssql query -q "SELECT * FROM dbo.CUSTOMERS" --limit 10
qadmcli mssql query -q "SELECT * FROM dbo.CUSTOMERS" --format json
```

## qadmcli CT Commands

### Check Status
```bash
qadmcli mssql ct status -t CUSTOMERS -s dbo
```

### Enable CT
```bash
# Enable on database (requires ALTER DATABASE)
qadmcli mssql ct enable-db -r 2 --auto-cleanup -U sa -P <password>

# Enable on table (requires ALTER permission)
qadmcli mssql ct enable-table -t CUSTOMERS -s dbo --track-columns -U admin -P <password>
```

### Query Changes
```bash
# Since specific version
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since-version 100

# Since timestamp
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since "2025-04-09 10:00:00"

# JSON output
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since-version 0 --format json
```

### Disable CT
```bash
# Disable on table
qadmcli mssql ct disable-table -t CUSTOMERS -s dbo -U admin -P <password>

# Disable on database (removes all history)
qadmcli mssql ct disable-db -U sa -P <password>
```

## Common Patterns

### Sync Pattern
```python
# 1. Get current version as baseline
last_version = get_last_sync_version()

# 2. Query changes
changes = ct.get_changes(since_version=last_version)

# 3. Process by operation type
for change in changes:
    if change.operation == 'I':
        target.insert(change.pk_values)
    elif change.operation == 'U':
        target.update(change.pk_values)
    elif change.operation == 'D':
        target.delete(change.pk_values)

# 4. Save new baseline
save_sync_version(changes[-1].version)
```

### Initial Load + Incremental Sync
```bash
# 1. Enable CT on database and table
qadmcli mssql ct enable-db -U sa -P <password>
qadmcli mssql ct enable-table -t CUSTOMERS -U admin -P <password>

# 2. Get initial version (after enabling CT)
qadmcli mssql ct changes -t CUSTOMERS --since-version 0 --limit 1
# Note the current version (e.g., 100)

# 3. Perform initial full load (export all data)

# 4. Subsequent incremental syncs
qadmcli mssql ct changes -t CUSTOMERS --since-version 100
# Process changes and update baseline version
```

## Troubleshooting

### "Minimum valid version" Error
```
Error: The minimum valid version is higher than the requested version.
```
**Cause**: Your baseline version is older than the retention period.
**Solution**: Perform a full refresh or increase retention period.

### "Primary key required" Error
```
Error: Table does not have a primary key. Change Tracking requires a primary key.
```
**Cause**: Table lacks a primary key.
**Solution**: Add a primary key before enabling CT.

### Permission Denied
```
Error: Insufficient permissions to enable Change Tracking
```
**Cause**: Current user lacks ALTER DATABASE or ALTER permission.
**Solution**: Use `-U` and `-P` to provide admin credentials.
