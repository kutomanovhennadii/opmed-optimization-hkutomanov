# activate.ps1 — quick launcher for project virtual environment
# Usage: .\activate.ps1
$venvPath = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    & $venvPath
} else {
    Write-Host "❌ Virtual environment not found. Run 'py -3.11 -m poetry install' first."
}
