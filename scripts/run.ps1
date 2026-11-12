param([string]$Config = 'configs/default.json')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$candidates = @(
    (Join-Path $projectRoot '.venv\Scripts\python.exe'),
    'python',
    'C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)
$selectedPython = $null
foreach ($candidate in $candidates) {
    try {
        & $candidate -c 'import numpy' 2>$null
        if ($LASTEXITCODE -eq 0) { $selectedPython = $candidate; break }
    } catch { continue }
}
if (-not $selectedPython) {
    throw 'No Python with NumPy found. Install Python 3.10+ and run: python -m pip install -r requirements.txt'
}
Write-Output "Using Python: $selectedPython"
& $selectedPython -m gardenrec run --config $Config
exit $LASTEXITCODE
