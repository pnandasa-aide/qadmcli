#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Setup MSSQL Change Tracking test environment using qadmcli
.DESCRIPTION
    Creates test tables and enables Change Tracking using qadmcli SQL commands
.EXAMPLE
    .\setup_mssql_ct.ps1
#>

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MSSQL Change Tracking Setup via qadmcli" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Check if qadmcli is available
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$qadmcli = Join-Path $scriptDir "..\qadmcli.ps1"
if (-not (Test-Path $qadmcli)) {
    $qadmcli = "qadmcli"
}

function Invoke-Qadmcli {
    param([string]$Command)
    Write-Host "> qadmcli $Command" -ForegroundColor DarkGray
    if ($qadmcli -eq "qadmcli") {
        Invoke-Expression "qadmcli $Command"
    } else {
        # Use call operator with the full path
        & $qadmcli @($Command.Split(' '))
    }
}

# Note: This script uses qadmcli commands. Some DDL/DML operations may require direct SQL execution.
# For now, we'll use sql query for SELECT operations and document the DDL steps.

Write-Host "`nNote: DDL operations (CREATE TABLE, ALTER TABLE) require direct SQL execution." -ForegroundColor Yellow
Write-Host "Please run the following SQL manually in SSMS or sqlcmd:" -ForegroundColor Yellow
Write-Host @"

-- Step 1: Check CT status
SELECT name, is_change_tracking_on FROM sys.databases WHERE name = DB_NAME();

-- Step 2: Create test table
IF OBJECT_ID('dbo.INSURANCE_PRODUCTS', 'U') IS NOT NULL DROP TABLE dbo.INSURANCE_PRODUCTS;
CREATE TABLE dbo.INSURANCE_PRODUCTS (
    PRODUCT_ID INT IDENTITY(100, 1) PRIMARY KEY,
    PRODUCT_CODE NVARCHAR(20) NOT NULL,
    PRODUCT_NAME NVARCHAR(100) NOT NULL,
    PRODUCT_TYPE NVARCHAR(20) NOT NULL,
    BASE_PREMIUM DECIMAL(10, 2) NOT NULL,
    STATUS NVARCHAR(10) DEFAULT 'ACTIVE',
    CREATED_AT DATETIME2 DEFAULT GETDATE(),
    UPDATED_AT DATETIME2 DEFAULT GETDATE()
);

-- Step 3: Enable CT on table
ALTER TABLE dbo.INSURANCE_PRODUCTS ENABLE CHANGE_TRACKING WITH (TRACK_COLUMNS_UPDATED = ON);

-- Step 4: Insert test data
INSERT INTO dbo.INSURANCE_PRODUCTS (PRODUCT_CODE, PRODUCT_NAME, PRODUCT_TYPE, BASE_PREMIUM, STATUS)
VALUES 
    ('PROD1001', 'Life Insurance Premium', 'LIFE', 500.00, 'ACTIVE'),
    ('PROD1002', 'Health Insurance Basic', 'HEALTH', 300.00, 'ACTIVE'),
    ('PROD1003', 'Car Insurance Full', 'AUTO', 800.00, 'ACTIVE'),
    ('PROD1004', 'Home Insurance Standard', 'PROPERTY', 450.00, 'ACTIVE'),
    ('PROD1005', 'Life Insurance Basic', 'LIFE', 250.00, 'ACTIVE');

"@ -ForegroundColor Cyan

Read-Host "Press Enter after running the SQL above to continue with CT testing..."

# Step 5: Verify CT using new CLI command
Write-Host "`n[Step 5] Verifying CT status using qadmcli mssql ct status..." -ForegroundColor Yellow
Invoke-Qadmcli 'mssql ct status -t INSURANCE_PRODUCTS -s dbo'

# Step 6: Query changes using new CLI command
Write-Host "`n[Step 6] Querying changes using qadmcli mssql ct changes..." -ForegroundColor Yellow
Invoke-Qadmcli 'mssql ct changes -t INSURANCE_PRODUCTS -s dbo --since-version 0'

# Step 7: Update a record (document only - requires manual execution)
Write-Host "`n[Step 7] To generate UPDATE operation, run:" -ForegroundColor Yellow
Write-Host "UPDATE dbo.INSURANCE_PRODUCTS SET STATUS = 'INACTIVE', UPDATED_AT = GETDATE() WHERE PRODUCT_ID = 100;" -ForegroundColor Cyan
Read-Host "Press Enter after running the UPDATE..."

# Step 8: Query changes again
Write-Host "`n[Step 8] Querying changes again to see UPDATE operation..." -ForegroundColor Yellow
Invoke-Qadmcli 'mssql ct changes -t INSURANCE_PRODUCTS -s dbo --since-version 0'

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "Setup complete! CT is now ready for testing." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "`nNext steps:"
Write-Host "  1. Test CT status:  qadmcli mssql ct status -t INSURANCE_PRODUCTS"
Write-Host "  2. Query changes:   qadmcli mssql ct changes -t INSURANCE_PRODUCTS --since-version 0"
Write-Host "  3. Test with JSON:  qadmcli mssql ct changes -t INSURANCE_PRODUCTS --since-version 0 --format json"
