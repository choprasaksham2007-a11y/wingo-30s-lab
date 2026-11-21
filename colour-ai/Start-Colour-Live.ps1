param([ValidateSet('collector', 'predictor')][string]$Mode = 'collector')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($Mode -eq 'collector') {
    $lockPath = Join-Path $PSScriptRoot 'wingo_investigation\collected_data\collector.lock'
    $pythonPath = (Get-Command python).Source
    $scriptArgument = 'wingo_investigation\collect_live.py'
    $metadata = Join-Path $PSScriptRoot 'results\collector_worker.json'
} else {
    $lockPath = Join-Path $PSScriptRoot 'results\category_learner.lock'
    $pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $scriptArgument = 'src\category_predictor.py watch'
    $metadata = Join-Path $PSScriptRoot 'results\neural_worker.json'
}
$lockHandle = [System.IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'ReadWrite')
try {
    try { $lockHandle.Lock(0, 1) }
    catch {
        Write-Host "$Mode is already running. Open its View-Live file to see output."
        exit 0
    }
    $lockHandle.Unlock(0, 1)
} finally { $lockHandle.Dispose() }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$stdout = Join-Path $PSScriptRoot "results\${Mode}_$stamp.log"
$stderr = Join-Path $PSScriptRoot "results\${Mode}_$stamp.errors.log"
$worker = Start-Process -FilePath $pythonPath -ArgumentList "-u $scriptArgument" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Start-Sleep -Seconds 2
if ($worker.HasExited) {
    Get-Content -LiteralPath $stdout
    Get-Content -LiteralPath $stderr
    throw "$Mode exited during startup. See the output above."
}
@{pid=$worker.Id; stdout=$stdout; stderr=$stderr; started_at=(Get-Date).ToString('o'); mode=$Mode} | ConvertTo-Json | Set-Content -LiteralPath $metadata
Write-Host "$Mode started in the background. Open its View-Live file to see output."
if ($Mode -eq 'collector') {
    Write-Host 'Keep plugged in and lid open. The screen may turn off. Manual Sleep pauses collection.'
}
