# verify_import.ps1
$env:PYTHONPATH = "C:\Repository\opmed-optimization\src"
Write-Host "Testing Python import..."
python -c "import opmed; import opmed.solver_core; print('✅ Import succeeded')"
if ($LASTEXITCODE -eq 0) {
    Write-Host "All good!"
} else {
    Write-Error "Import failed — check folder structure or PYTHONPATH."
}
