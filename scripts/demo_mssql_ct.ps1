#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Full MSSQL Change Tracking Demo Script
.DESCRIPTION
    Demonstrates the complete CT workflow including:
    - Enable CT on database and table
    - Insert/update/delete data
    - Query changes
    - Disable CT
.EXAMPLE
    .\demo_mssql_ct.ps1 -AdminUser gstgdblogin -AdminPassword 'tar53t@dm1n'
#>

[CmdletBinding()]
param(
    [string]$AdminUser = $env:MSSQL_ADMIN_USER,
    [string]$AdminPassword = $env:MSSQL_ADMIN_PASSWORD,
    [string]$TableName = "CT_DEMO_CUSTOMERS",
    [string]$Schema = "dbo",
    [switch]$SkipCleanup
)

$ErrorActionPreference = "Stop"

# Colors
$Cyan = "Cyan"
$Green = "Green"
$Yellow = "Yellow"
$Red = "Red"

# Helper function to run qadmcli commands
function Invoke-Qadmcli {
    param(
        [string]$Arguments,
        [switch]$IgnoreError
    )
    
    $cmd = "qadmcli $Arguments"
    Write-Host "> $cmd" -ForegroundColor DarkGray
    
    try {
        $output = & podman run -it --rm `
            -e AS400_USER=$env:AS400_USER `
            -e AS400_PASSWORD=$env:AS400_PASSWORD `
            -e MSSQL_USER=$env:MSSQL_USER `
            -e MSSQL_PASSWORD=$env:MSSQL_PASSWORD `
            -v "${PSScriptRoot}/..:/app:Z" `
            qadmcli @($Arguments.Split(' '))
        
        return $output
    }
    catch {
        if (-not $IgnoreError) {
            Write-Host "Error: $_" -ForegroundColor $Red
        }
        return $null
    }
}

function Show-Header {
    param([string]$Title)
    Write-Host "`n============================================================" -ForegroundColor $Cyan
    Write-Host "  $Title" -ForegroundColor $Cyan
    Write-Host "============================================================" -ForegroundColor $Cyan
}

function Show-Step {
    param([int]$Number, [string]$Description)
    Write-Host "`n[Step $Number] $Description" -ForegroundColor $Yellow
}

function Wait-ForKey {
    param([string]$Message = "Press Enter to continue...")
    Write-Host "`n$Message" -ForegroundColor DarkGray
    Read-Host
}

# Main Demo Script
Show-Header "MSSQL Change Tracking Full Demo"

Write-Host @"

This demo will walk you through the complete Change Tracking workflow:

1. Check current CT status
2. Enable CT on database (if not enabled)
3. Create demo table with primary key
4. Enable CT on table
5. Insert test data (generates 'I' operations)
6. Query changes
7. Update data (generates 'U' operations)
8. Query changes again
9. Delete data (generates 'D' operations)
10. Query final changes
11. Cleanup (disable CT on table)

"@ -ForegroundColor White

if (-not $AdminUser) {
    $AdminUser = Read-Host "Enter MSSQL admin username"
}
if (-not $AdminPassword) {
    $AdminPassword = Read-Host "Enter MSSQL admin password" -AsSecureString | ConvertFrom-SecureString
}

# Step 1: Check CT Status
Show-Step 1 "Checking CT status for $Schema.$TableName"
Invoke-Qadmcli "mssql ct status -t $TableName -s $Schema" -IgnoreError

# Step 2: Enable CT on Database
Show-Step 2 "Enabling CT on database"
Write-Host "Enabling CT with 2-day retention and auto-cleanup..." -ForegroundColor $Cyan
Invoke-Qadmcli "mssql ct enable-db -r 2 --auto-cleanup -U $AdminUser -P '$AdminPassword'"

# Step 3: Create Demo Table
Show-Step 3 "Creating demo table: $Schema.$TableName"
Write-Host "Creating table with primary key (required for CT)..." -ForegroundColor $Cyan

# Use direct SQL via Python since we don't have MSSQL execute command
$createTableSQL = @"
IF OBJECT_ID('$Schema.$TableName', 'U') IS NOT NULL
    DROP TABLE $Schema.$TableName;

CREATE TABLE $Schema.$TableName (
    CUST_ID INT IDENTITY(1000, 1) PRIMARY KEY,
    FIRST_NAME NVARCHAR(50) NOT NULL,
    LAST_NAME NVARCHAR(50) NOT NULL,
    EMAIL NVARCHAR(100),
    STATUS NVARCHAR(20) DEFAULT 'ACTIVE',
    CREATED_AT DATETIME2 DEFAULT GETDATE(),
    UPDATED_AT DATETIME2 DEFAULT GETDATE()
);
"@

Write-Host "Table creation SQL:" -ForegroundColor DarkGray
Write-Host $createTableSQL -ForegroundColor DarkGray
Write-Host "`nNote: Table creation requires direct SQL execution (not available via CLI)" -ForegroundColor $Yellow
Write-Host "Please run the above SQL in SSMS or sqlcmd, then press Enter to continue..." -ForegroundColor $Yellow
Read-Host

# Step 4: Enable CT on Table
Show-Step 4 "Enabling CT on table $Schema.$TableName"
Invoke-Qadmcli "mssql ct enable-table -t $TableName -s $Schema --track-columns -U $AdminUser -P '$AdminPassword'"

# Step 5: Verify CT is Enabled
Show-Step 5 "Verifying CT is enabled"
Invoke-Qadmcli "mssql ct status -t $TableName -s $Schema"

# Step 6: Insert Test Data
Show-Step 6 "Inserting test data (generates 'I' - Insert operations)"
Write-Host @"

Please run the following SQL to insert test data:

INSERT INTO $Schema.$TableName (FIRST_NAME, LAST_NAME, EMAIL, STATUS)
VALUES 
    ('John', 'Doe', 'john.doe@example.com', 'ACTIVE'),
    ('Jane', 'Smith', 'jane.smith@example.com', 'ACTIVE'),
    ('Bob', 'Johnson', 'bob.j@example.com', 'PENDING'),
    ('Alice', 'Williams', 'alice.w@example.com', 'ACTIVE'),
    ('Charlie', 'Brown', 'charlie.b@example.com', 'ACTIVE');

"@ -ForegroundColor $Cyan

Wait-ForKey "After inserting data, press Enter to query changes..."

# Step 7: Query Changes (should show 'I' operations)
Show-Step 7 "Querying changes (expecting 'I' - Insert operations)"
Invoke-Qadmcli "mssql ct changes -t $TableName -s $Schema --since-version 0"

# Step 8: Update Data
Show-Step 8 "Updating data (generates 'U' - Update operations)"
Write-Host @"

Please run the following SQL to update some records:

UPDATE $Schema.$TableName 
SET STATUS = 'INACTIVE', 
    UPDATED_AT = GETDATE(),
    EMAIL = 'john.doe.updated@example.com'
WHERE CUST_ID = 1000;

UPDATE $Schema.$TableName 
SET STATUS = 'ACTIVE',
    UPDATED_AT = GETDATE()
WHERE CUST_ID = 1002;

"@ -ForegroundColor $Cyan

Wait-ForKey "After updating data, press Enter to query changes..."

# Step 9: Query Changes Again (should show 'U' operations)
Show-Step 9 "Querying changes again (expecting 'I' and 'U' operations)"
Invoke-Qadmcli "mssql ct changes -t $TableName -s $Schema --since-version 0"

# Step 10: Delete Data
Show-Step 10 "Deleting data (generates 'D' - Delete operations)"
Write-Host @"

Please run the following SQL to delete a record:

DELETE FROM $Schema.$TableName WHERE CUST_ID = 1004;

"@ -ForegroundColor $Cyan

Wait-ForKey "After deleting data, press Enter to query final changes..."

# Step 11: Query Final Changes (should show 'I', 'U', and 'D' operations)
Show-Step 11 "Querying final changes (expecting 'I', 'U', and 'D' operations)"
Invoke-Qadmcli "mssql ct changes -t $TableName -s $Schema --since-version 0"

# Step 12: Demonstrate JSON Output
Show-Step 12 "Showing JSON output format"
Invoke-Qadmcli "mssql ct changes -t $TableName -s $Schema --since-version 0 --format json"

# Step 13: Show Version-Based Query
Show-Step 13 "Demonstrating version-based querying"
Write-Host @"

The CT system maintains a version counter. You can query changes since a specific version:

1. First, note the highest SYS_CHANGE_VERSION from the previous output
2. Then query changes since that version to get only new changes

Example:
  qadmcli mssql ct changes -t $TableName -s $Schema --since-version 5

"@ -ForegroundColor $Cyan

# Cleanup
if (-not $SkipCleanup) {
    Show-Step 14 "Cleanup: Disabling CT on table"
    Write-Host @"

This will disable Change Tracking on the demo table.
Note: This does NOT delete the table data, only stops tracking changes.

"@ -ForegroundColor $Yellow
    
    $cleanup = Read-Host "Disable CT on table? (y/N)"
    if ($cleanup -eq 'y' -or $cleanup -eq 'Y') {
        Invoke-Qadmcli "mssql ct disable-table -t $TableName -s $Schema -U $AdminUser -P '$AdminPassword'"
        
        Write-Host "`nNote: To drop the demo table, run:" -ForegroundColor $Cyan
        Write-Host "  DROP TABLE $Schema.$TableName;" -ForegroundColor DarkGray
    }
}

# Summary
Show-Header "Demo Complete!"

Write-Host @"

Summary of CT Operations:
========================

I = Insert (new records)
U = Update (modified records)
D = Delete (removed records)

Key Points:
-----------
1. CT tracks ONLY Primary Key values + operation type
2. CT does NOT store full row data (use CDC for that)
3. CT requires database-level enable FIRST, then table-level
4. Tables MUST have a primary key to enable CT
5. CT has minimal performance impact compared to CDC
6. Old CT data is automatically cleaned up based on retention period

Common Commands:
----------------
# Check status
qadmcli mssql ct status -t $TableName -s $Schema

# Enable CT
qadmcli mssql ct enable-db -U $AdminUser -P <password>
qadmcli mssql ct enable-table -t $TableName -U $AdminUser -P <password>

# Query changes
qadmcli mssql ct changes -t $TableName --since-version 0
qadmcli mssql ct changes -t $TableName --since "2025-04-09 10:00:00"
qadmcli mssql ct changes -t $TableName --since-version 0 --format json

# Disable CT
qadmcli mssql ct disable-table -t $TableName -U $AdminUser -P <password>
qadmcli mssql ct disable-db -U $AdminUser -P <password>

For more details, see: docs/mssql-change-tracking.md
"@ -ForegroundColor $Green
