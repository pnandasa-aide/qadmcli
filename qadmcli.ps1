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

# Build environment variables
$envVars = @(
    "-e", "AS400_USER=$env:AS400_USER",
    "-e", "AS400_PASSWORD=$env:AS400_PASSWORD",
    "-e", "MSSQL_USER=$env:MSSQL_USER",
    "-e", "MSSQL_PASSWORD=$env:MSSQL_PASSWORD"
)

# Volume mount (with :Z for SELinux)
$volumeMount = "-v", "${PSScriptRoot}:/app:Z"

# Run container
# Filter out the '--' separator if present (used to stop PowerShell from interpreting arguments)
$filteredArgs = $Arguments | Where-Object { $_ -ne '--' }
Write-Host "🚀 Running: qadmcli $filteredArgs" -ForegroundColor Cyan

# Suppress TTY warning on Windows by redirecting stderr
$podmanArgs = @("run", "-it", "--rm", "--name", $ContainerName) + $envVars + $volumeMount + @($ImageName) + $filteredArgs
& podman @podmanArgs 2>&1 | Where-Object { $_ -notmatch "Failed to obtain TTY size" }

exit $LASTEXITCODE
