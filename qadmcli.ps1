#!/usr/bin/env pwsh
<#
.SYNOPSIS
    QADM CLI Container Helper Script for PowerShell
.DESCRIPTION
    Builds and runs qadmcli container with proper environment variables and volume mounts
.EXAMPLE
    .\qadmcli.ps1 connection test
    .\qadmcli.ps1 table list -l GSLIBTST
    .\qadmcli.ps1 table convert -s config/schema/subscriber.yaml --source-db DB2 --target-db MSSQL
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

# Load environment variables from .env file
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)\s*=\s*(.*)\s*$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim().Trim("'").Trim('"')
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Container configuration
$ImageName = "qadmcli"
$ContainerName = "qadmcli-$(Get-Random -Minimum 1000 -Maximum 9999)"

# Check if image exists
$imageExists = podman images --format "{{.Repository}}" | Select-String -Pattern "^localhost/$ImageName$"

if (-not $imageExists) {
    Write-Host "🔨 Building qadmcli image..." -ForegroundColor Yellow
    podman build -t $ImageName -f (Join-Path $PSScriptRoot "Containerfile") $PSScriptRoot
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Build failed!" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Build successful!" -ForegroundColor Green
} else {
    Write-Host "📦 Using existing image: $ImageName" -ForegroundColor Cyan
}

# Determine which credentials are needed based on command
$filteredArgs = $Arguments | Where-Object { $_ -ne '--' }

# Check if this is an MSSQL operation:
# 1. Explicit --target mssql flag
# 2. Command starts with 'mssql' (e.g., 'mssql ct status')
# 3. Command contains 'mssql' anywhere (for subcommands)
$hasTargetMSSQL = ($filteredArgs -contains '--target' -or $filteredArgs -contains '-t') -and 
                  ($filteredArgs -contains 'mssql')
$isMSSQLCommand = $filteredArgs.Count -gt 0 -and ($filteredArgs[0] -eq 'mssql' -or 
                  ($filteredArgs -join ' ') -match '^mssql\s')
$targetMSSQL = $hasTargetMSSQL -or $isMSSQLCommand

# Build environment variables based on target
$envVars = @()

if ($targetMSSQL) {
    # MSSQL target - require MSSQL credentials
    if (-not $env:MSSQL_USER -or -not $env:MSSQL_PASSWORD) {
        Write-Host "⚠️  Warning: MSSQL_USER and/or MSSQL_PASSWORD not set in .env file" -ForegroundColor Yellow
        Write-Host "   These are required for --target mssql operations" -ForegroundColor Yellow
    }
    $envVars += @(
        "-e", "MSSQL_USER=$env:MSSQL_USER",
        "-e", "MSSQL_PASSWORD=$env:MSSQL_PASSWORD"
    )
    # Also pass AS400 credentials if available (for mixed operations)
    if ($env:AS400_USER -and $env:AS400_PASSWORD) {
        $envVars += @(
            "-e", "AS400_USER=$env:AS400_USER",
            "-e", "AS400_PASSWORD=$env:AS400_PASSWORD"
        )
    }
} else {
    # Default/AS400 target - require AS400 credentials
    if (-not $env:AS400_USER -or -not $env:AS400_PASSWORD) {
        Write-Host "⚠️  Warning: AS400_USER and/or AS400_PASSWORD not set in .env file" -ForegroundColor Yellow
        Write-Host "   These are required for AS400 operations (use --target mssql for MSSQL)" -ForegroundColor Yellow
    }
    $envVars += @(
        "-e", "AS400_USER=$env:AS400_USER",
        "-e", "AS400_PASSWORD=$env:AS400_PASSWORD"
    )
    # Also pass MSSQL credentials if available (for mixed operations)
    if ($env:MSSQL_USER -and $env:MSSQL_PASSWORD) {
        $envVars += @(
            "-e", "MSSQL_USER=$env:MSSQL_USER",
            "-e", "MSSQL_PASSWORD=$env:MSSQL_PASSWORD"
        )
    }
}

# Volume mount (with :Z for SELinux)
$volumeMount = "-v", "${PSScriptRoot}:/app:Z"

# Run container
Write-Host "🚀 Running: qadmcli $($filteredArgs -join ' ')" -ForegroundColor Cyan

# Suppress TTY warning on Windows by redirecting stderr
$podmanArgs = @("run", "-it", "--rm", "--name", $ContainerName) + $envVars + $volumeMount + @($ImageName) + $filteredArgs
& podman @podmanArgs 2>&1 | Where-Object { $_ -notmatch "Failed to obtain TTY size" }

exit $LASTEXITCODE
