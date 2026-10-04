param(
  [string]$StartDate = "",
  [string]$EndDate = "",
  [int]$MaxActivities = 0,
  [int]$MaxDetailActivities = 0,
  [int]$MaxGarminWorkouts = 0,
  [int]$OverlapDays = 7,
  [switch]$FullRefresh,
  [switch]$IncludeGarminWorkouts,
  [switch]$SkipGarmin,
  [switch]$SkipHevy,
  [switch]$SkipGarminWorkouts,
  [switch]$SkipExtraDailyMetrics,
  [switch]$SkipDetailedProfile,
  [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot
. (Join-Path $PSScriptRoot "load_env.ps1") -Path (Join-Path $ProjectRoot ".env")

if ($env:DATABASE_BACKEND -eq "postgres") {
  if ($FullRefresh -or $IncludeGarminWorkouts -or $StartDate -or $EndDate -or $MaxActivities -or $MaxDetailActivities -or $MaxGarminWorkouts -or $OverlapDays -ne 7 -or $SkipExtraDailyMetrics) {
    throw "Custom legacy import options are unavailable in PostgreSQL mode. Use the default transactional sync; JSON originals are read-only migration references."
  }
  if ($ValidateOnly) {
    & docker compose exec -T api python -m dashboard.database_cli status
  } else {
    $mode = if ($SkipGarmin -and $SkipHevy) { "generate" } elseif ($SkipGarmin) { "sync-hevy" } elseif ($SkipHevy) { "sync-garmin" } else { "sync" }
    & docker compose exec -T api python -m dashboard.database_cli run --mode $mode
  }
  if ($LASTEXITCODE -ne 0) { throw "Transactional database operation failed. Previous revision was preserved." }
  exit 0
}

if (-not $EndDate) {
  $EndDate = Get-Date -Format "yyyy-MM-dd"
}
$fallbackDate = if ($env:TRAINING_SYNC_START_DATE) { $env:TRAINING_SYNC_START_DATE } else { "2024-01-01" }
if ($OverlapDays -lt 0) {
  throw "OverlapDays must be non-negative."
}
if (-not $StartDate) {
  if ($FullRefresh -or $SkipGarmin) {
    $StartDate = $fallbackDate
  } else {
    $StartDate = & python scripts\compute_garmin_sync_window.py --end-date $EndDate --fallback-date $fallbackDate --overlap-days $OverlapDays
    if ($LASTEXITCODE -ne 0) {
      throw "Could not determine Garmin incremental start date."
    }
    $StartDate = "$StartDate".Trim()
  }
}
try {
  $startParsed = [datetime]::ParseExact($StartDate, "yyyy-MM-dd", [cultureinfo]::InvariantCulture)
  $endParsed = [datetime]::ParseExact($EndDate, "yyyy-MM-dd", [cultureinfo]::InvariantCulture)
} catch {
  throw "StartDate and EndDate must use yyyy-MM-dd."
}
if ($startParsed -gt $endParsed) {
  throw "StartDate must be on or before EndDate."
}
if ($MaxActivities -le 0) {
  $MaxActivities = if ($env:TRAINING_SYNC_MAX_ACTIVITIES) { [int]$env:TRAINING_SYNC_MAX_ACTIVITIES } else { 5000 }
}
if ($MaxDetailActivities -le 0) {
  $MaxDetailActivities = if ($env:TRAINING_SYNC_MAX_DETAIL_ACTIVITIES) { [int]$env:TRAINING_SYNC_MAX_DETAIL_ACTIVITIES } else { 300 }
}
if ($MaxGarminWorkouts -le 0) {
  $MaxGarminWorkouts = if ($env:TRAINING_SYNC_MAX_GARMIN_WORKOUTS) { [int]$env:TRAINING_SYNC_MAX_GARMIN_WORKOUTS } else { 500 }
}

$missing = @()
if (-not $SkipGarmin) {
  if (-not $env:GARMIN_EMAIL) { $missing += "GARMIN_EMAIL" }
  if (-not $env:GARMIN_PASSWORD) { $missing += "GARMIN_PASSWORD" }
}
if (-not $SkipHevy -and -not $env:HEVY_API_KEY) {
  $missing += "HEVY_API_KEY"
}
if ($missing.Count -gt 0) {
  throw "Missing credentials in $ProjectRoot\.env: $($missing -join ', ')"
}

Write-Host "AscentIQ unified training sync" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Mode: $(if ($FullRefresh) { 'full refresh' } else { 'incremental' })"
Write-Host "Range: $StartDate to $EndDate"
Write-Host "Sources: Garmin=$(-not $SkipGarmin), Hevy=$(-not $SkipHevy)"
Write-Host "Credentials found. Secret values were not displayed."

if ($ValidateOnly) {
  Write-Host "Configuration is valid." -ForegroundColor Green
  exit 0
}

function Invoke-Python {
  & python @args
  if ($LASTEXITCODE -ne 0) {
    throw "Python command failed: python $($args -join ' ')"
  }
}

if (-not $SkipGarmin) {
  Write-Host ""
  Write-Host "[1/4] Downloading Garmin activities and health context..." -ForegroundColor Cyan
  $garminArgs = @{
    StartDate = $StartDate
    EndDate = $EndDate
    MaxActivities = $MaxActivities
    MaxDetailActivities = $MaxDetailActivities
    SkipModelRebuild = $true
  }
  if (-not $FullRefresh) {
    $garminArgs.Incremental = $true
  }
  if ($SkipExtraDailyMetrics) {
    $garminArgs.SkipExtraDailyMetrics = $true
  }
  & (Join-Path $PSScriptRoot "run_garmin_mcp_full_import.ps1") @garminArgs

  if ($IncludeGarminWorkouts -and -not $SkipGarminWorkouts) {
    Write-Host "Downloading Garmin saved workouts/routines..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "run_garmin_workout_import.ps1") -MaxWorkouts $MaxGarminWorkouts
  }
}

if (-not $SkipHevy) {
  Write-Host ""
  Write-Host "[2/4] Downloading Hevy workouts..." -ForegroundColor Cyan
  if ($FullRefresh) {
    Invoke-Python scripts\fetch_hevy_workouts.py --output data\hevy_api_exports\hevy_workouts_latest.json
  } else {
    Invoke-Python scripts\fetch_hevy_workouts.py --output data\hevy_api_exports\hevy_workouts_latest.json --incremental --no-archive
  }
  Write-Host "Consolidating Hevy sets with Garmin strength activities..." -ForegroundColor Cyan
  Invoke-Python scripts\import_hevy_workouts.py --input data\hevy_api_exports\hevy_workouts_latest.json --format api
}

Write-Host ""
Write-Host "[3/4] Rebuilding performance models and charts..." -ForegroundColor Cyan
Invoke-Python scripts\build_performance_management_model.py
Invoke-Python scripts\build_last_3_weeks_pmc_chart.py
Invoke-Python scripts\build_training_execution_indexes.py
Invoke-Python scripts\build_current_performance_dashboard.py

if (-not $SkipDetailedProfile) {
  & (Join-Path $PSScriptRoot "build_detailed_profile.ps1") -ProjectRoot $ProjectRoot
}

Write-Host ""
Write-Host "[4/4] Building sync summary..." -ForegroundColor Cyan
Invoke-Python scripts\build_training_sync_summary.py

Write-Host ""
Write-Host "DONE. Selected sources and local performance models are synchronized." -ForegroundColor Green
Write-Host "Summary: $ProjectRoot\analysis\context\training_sync_latest.md"
