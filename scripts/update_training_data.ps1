param([switch]$SkipGarmin,[switch]$SkipHevy,[switch]$ValidateOnly)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if ($ValidateOnly) {
    & docker compose exec -T api python -m dashboard.database_cli status
} else {
    $mode = if ($SkipGarmin -and $SkipHevy) { "generate" } elseif ($SkipGarmin) { "sync-hevy" } elseif ($SkipHevy) { "sync-garmin" } else { "sync" }
    & docker compose exec -T api python -m dashboard.database_cli run --mode $mode
}
if ($LASTEXITCODE -ne 0) { throw "The update failed. Check the private dashboard job status." }
