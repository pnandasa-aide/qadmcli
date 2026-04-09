#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run the automated MSSQL Change Tracking demo in container
.DESCRIPTION
    Runs demo_mssql_ct_auto.py inside the qadmcli container
.EXAMPLE
    .\run_ct_demo.ps1
#>

$ErrorActionPreference = "Stop"

# Get script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  MSSQL Change Tracking - Automated Demo" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Load environment variables
$envFile = Join-Path $projectDir ".env"
if (Test-Path $envFile) {
    Write-Host "Loading environment from $envFile..." -ForegroundColor DarkGray
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)\s*=\s*(.*)\s*$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim().Trim("'").Trim('"')
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Check if image exists
$imageExists = podman images --format "{{.Repository}}" | Select-String -Pattern "^localhost/qadmcli$"

if (-not $imageExists) {
    Write-Host "Building qadmcli image..." -ForegroundColor Yellow
    podman build -t qadmcli -f (Join-Path $projectDir "Containerfile") $projectDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Build failed!" -ForegroundColor Red
        exit 1
    }
}

Write-Host "`nRunning automated CT demo..." -ForegroundColor Green
Write-Host "This will:" -ForegroundColor White
Write-Host "  1. Create a demo table" -ForegroundColor White
Write-Host "  2. Enable CT on database and table" -ForegroundColor White
Write-Host "  3. Insert 5 records (generates 'I' operations)" -ForegroundColor White
Write-Host "  4. Update 2 records (generates 'U' operations)" -ForegroundColor White
Write-Host "  5. Delete 1 record (generates 'D' operations)" -ForegroundColor White
Write-Host "  6. Query and display all changes" -ForegroundColor White
Write-Host "  7. Cleanup (disable CT and drop table)" -ForegroundColor White
Write-Host ""

$continue = Read-Host "Continue? (Y/n)"
if ($continue -eq 'n' -or $continue -eq 'N') {
    Write-Host "Demo cancelled." -ForegroundColor Yellow
    exit 0
}

# Run the demo script in container
$containerName = "qadmcli-demo-$(Get-Random -Minimum 1000 -Maximum 9999)"

$envVars = @(
    "-e", "AS400_USER=$env:AS400_USER",
    "-e", "AS400_PASSWORD=$env:AS400_PASSWORD",
    "-e", "MSSQL_USER=$env:MSSQL_USER",
    "-e", "MSSQL_PASSWORD=$env:MSSQL_PASSWORD"
)

$volumeMount = "-v", "${projectDir}:/app:Z"

Write-Host "`nStarting demo container..." -ForegroundColor Cyan

# Run python script directly
$podmanArgs = @(
    "run", "-it", "--rm",
    "--name", $containerName
) + $envVars + $volumeMount + @(
    "qadmcli",
    "python", "/app/scripts/demo_mssql_ct_auto.py"
)

& podman @podmanArgs 2>&1 | Where-Object { $_ -notmatch "Failed to obtain TTY size" }

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "`n============================================================" -ForegroundColor Green
    Write-Host "  Demo completed successfully!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "`n============================================================" -ForegroundColor Red
    Write-Host "  Demo failed with exit code: $exitCode" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red
}

exit $exitCode
