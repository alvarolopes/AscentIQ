param(
  [string]$StartDate = "2024-01-01",
  [string]$EndDate = (Get-Date -Format "yyyy-MM-dd"),
  [int]$MaxActivities = 5000,
  [int]$MaxDetailActivities = 300,
  [switch]$Incremental,
  [switch]$SkipExtraDailyMetrics,
  [switch]$SkipModelRebuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot
. (Join-Path $PSScriptRoot "load_env.ps1") -Path (Join-Path $ProjectRoot ".env")
New-Item -ItemType Directory -Force -Path data\garmin_mcp_exports | Out-Null
$GarminMcpCommand = if ($env:GARMIN_MCP_COMMAND) { $env:GARMIN_MCP_COMMAND } else { "mcp-garmin" }

Write-Host "AscentIQ Garmin MCP $(if ($Incremental) { 'incremental' } else { 'full' }) import" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Range: $StartDate to $EndDate"
Write-Host "Activity details: newest $MaxDetailActivities activities"
Write-Host ""

if (-not $env:GARMIN_EMAIL) {
  $env:GARMIN_EMAIL = Read-Host "Garmin email"
}

if (-not $env:GARMIN_PASSWORD) {
  $securePassword = Read-Host "Garmin password" -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
  try {
    $env:GARMIN_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  }
  finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
  }
}

Write-Host ""
function Invoke-Python {
  & python @args
  if ($LASTEXITCODE -ne 0) {
    throw "Python command failed with exit code $LASTEXITCODE"
  }
}

if (-not $Incremental) {
  Write-Host "Testing MCP server tools..." -ForegroundColor Cyan
  Invoke-Python scripts\fetch_garmin_mcp_snapshot.py --server-command $GarminMcpCommand --list-tools | Out-File -FilePath data\garmin_mcp_exports\last_tools_check.json -Encoding utf8
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$mode = if ($Incremental) { "incremental" } else { "full" }
$snapshot = "data\garmin_mcp_exports\garmin_mcp_${mode}_${StartDate}_to_${EndDate}_$stamp.json"

$dailyArgs = @()
if (-not $SkipExtraDailyMetrics) {
  $dailyArgs += @("--daily-tool", "get_daily_summary")
  if (-not $Incremental) {
    $dailyArgs += @("--daily-tool", "get_heart_rates")
    $dailyArgs += @("--daily-tool", "get_stress_data")
    $dailyArgs += @("--daily-tool", "get_hrv_data")
    $dailyArgs += @("--daily-tool", "get_body_battery")
    $dailyArgs += @("--daily-tool", "get_steps_data")
    $dailyArgs += @("--daily-tool", "get_spo2_data")
    $dailyArgs += @("--daily-tool", "get_respiration_data")
    $dailyArgs += @("--daily-tool", "get_resting_heart_rate")
    $dailyArgs += @("--daily-tool", "get_intensity_minutes")
    $dailyArgs += @("--daily-tool", "get_training_readiness")
    $dailyArgs += @("--daily-tool", "get_training_status")
    $dailyArgs += @("--daily-tool", "get_max_metrics")
    $dailyArgs += @("--daily-tool", "get_fitness_age")
  }
}

$rangeArgs = @()
$profileArgs = @()
$knownArgs = @()
if ($Incremental) {
  $knownArgs += @("--known-activity-history", "data\training_history.json", "--skip-profile")
} else {
  $rangeArgs += @("--range-tool", "get_body_composition", "--range-tool", "get_weigh_ins")
  $profileArgs += @(
    "--profile-tool", "get_server_version",
    "--profile-tool", "get_user_profile",
    "--profile-tool", "get_personal_records",
    "--profile-tool", "get_workouts",
    "--profile-tool", "get_last_activity"
  )
}


$detailArgs = @(
  "--activity-detail-tool", "get_activity",
  "--activity-detail-tool", "get_activity_details",
  "--activity-detail-tool", "get_activity_splits",
  "--activity-detail-tool", "get_activity_hr_zones",
  "--activity-detail-tool", "get_activity_gear",
  "--activity-detail-tool", "get_activity_weather",
  "--activity-detail-tool", "get_activity_exercise_sets",
  "--max-detail-activities", $MaxDetailActivities
)

Write-Host "Capturing Garmin MCP snapshot..." -ForegroundColor Cyan
Invoke-Python scripts\fetch_garmin_mcp_snapshot.py `
  --server-command $GarminMcpCommand `
  --all-activities `
  --max-activities $MaxActivities `
  --start-date $StartDate `
  --end-date $EndDate `
  --output $snapshot `
  @dailyArgs `
  @rangeArgs `
  @profileArgs `
  @knownArgs `
  @detailArgs

Write-Host "Importing snapshot into local AscentIQ history..." -ForegroundColor Cyan
Invoke-Python scripts\import_garmin_mcp_snapshot.py --input $snapshot --since $StartDate

if (-not $SkipModelRebuild) {
  Write-Host "Rebuilding models and charts..." -ForegroundColor Cyan
  Invoke-Python scripts\build_performance_management_model.py
  Invoke-Python scripts\build_last_3_weeks_pmc_chart.py
  Invoke-Python scripts\build_training_execution_indexes.py
  Invoke-Python scripts\build_current_performance_dashboard.py
}

Write-Host ""
Write-Host "DONE. Snapshot: $snapshot" -ForegroundColor Green
Write-Host "You can return to Codex now."
