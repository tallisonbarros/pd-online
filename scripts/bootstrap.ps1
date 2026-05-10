$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\\python.exe"
$envFile = Join-Path $projectRoot ".env"
$envExampleFile = Join-Path $projectRoot ".env.example"

if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
}

if (-not (Test-Path $pythonExe)) {
    throw "Nao foi possivel localizar o Python da virtualenv em $pythonExe"
}

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r (Join-Path $projectRoot "requirements-dev.txt")

if (-not (Test-Path $envFile) -and (Test-Path $envExampleFile)) {
    Copy-Item $envExampleFile $envFile
}

& $pythonExe (Join-Path $projectRoot "manage.py") migrate

Write-Host "Bootstrap concluido. Use scripts\\dev.ps1 para subir o servidor e scripts\\stop-dev.ps1 para limpar instancias antigas."
