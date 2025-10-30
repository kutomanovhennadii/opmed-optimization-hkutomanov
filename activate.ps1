# activate.ps1 — quick launcher for project virtual environment
# Usage: .\activate.ps1

# 1) Activate local virtual environment
$venvPath = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    & $venvPath
} else {
    Write-Host "❌ Virtual environment not found. Run 'py -3.11 -m poetry install' first."
    return
}

# 2) Try to locate Poetry dynamically (avoid PATH duplicates)
$poetryCandidates = @(
    (Join-Path $env:APPDATA "Python\Python311\Scripts"),
    (Join-Path $env:APPDATA "Python\Scripts"),
    (Join-Path $env:APPDATA "pypoetry\venv\Scripts")
)

$poetryFound = $false
foreach ($path in $poetryCandidates) {
    $exe = Join-Path $path "poetry.exe"
    if (Test-Path $exe) {
        if (-not ($env:PATH -split ';' | Where-Object { $_ -eq $path })) {
            $env:PATH += ";$path"
        }
        $poetryFound = $true
        Write-Host "✅ Poetry detected at: $path"
        try { poetry --version | Write-Host } catch {}
        break
    }
}

if (-not $poetryFound) {
    Write-Host "⚠️ Poetry not found on this system."
    Write-Host "   → Install: (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -"
}

Write-Host "💡 Virtual environment ready."
