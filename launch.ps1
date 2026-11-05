$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'First setup downloads Python packages, including the CPU AI runtime (several hundred MB).'
    Write-Host 'Everything is installed inside this folder. No administrator rights are needed.'
    $answer = Read-Host 'Continue? [Y/N]'
    if ($answer -notmatch '^[Yy]$') { exit }
    $candidates = @()
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $fromLauncher = & $launcher.Source -3 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0) { $candidates += $fromLauncher }
    }
    $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundled) { $candidates += $bundled }
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython -and $systemPython.Source -notlike '*WindowsApps*') { $candidates += $systemPython.Source }
    $selected = $null
    foreach ($candidate in $candidates) {
        & $candidate -c 'import sys, tkinter, venv; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { $selected = $candidate; break }
    }
    if (-not $selected) { throw 'Install 64-bit Python 3.12 from python.org with Tcl/Tk and pip enabled, then run Start.cmd again.' }
    & $selected -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated Python environment.' }
}
Write-Host 'Checking for updates...'
$updateJson = & $venvPython (Join-Path $PSScriptRoot 'updater.py')
if ($LASTEXITCODE -ne 0) { throw 'Update helper failed. Your installed files have been kept.' }
$release = $updateJson | ConvertFrom-Json
Write-Host $release.status
$releasePath = $release.path
$env:HAZMOB_HOME = $PSScriptRoot
$requirementsPath = Join-Path $releasePath 'requirements.txt'
$requirementsHash = (Get-FileHash -LiteralPath $requirementsPath -Algorithm SHA256).Hash
$hashMarker = Join-Path $PSScriptRoot '.venv\requirements-sha256'
$ready = Join-Path $PSScriptRoot '.venv\setup-complete'
if (-not (Test-Path -LiteralPath $ready)) {
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip setup failed. Check the message above.' }
    & $venvPython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw 'AI runtime installation failed. Run Start.cmd again to retry.' }
    & $venvPython -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Package installation failed. Run Start.cmd again to retry.' }
    & $venvPython -m pip freeze | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'installed-versions.txt')
    Set-Content -LiteralPath $ready -Value 'ready'
    Set-Content -LiteralPath $hashMarker -Value $requirementsHash
}
# Existing installations can adopt the matching base requirements without reinstalling.
if (-not (Test-Path -LiteralPath $hashMarker)) {
    $baseHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'requirements.txt') -Algorithm SHA256).Hash
    Set-Content -LiteralPath $hashMarker -Value $baseHash
}
if ((Get-Content -Raw -LiteralPath $hashMarker).Trim() -ne $requirementsHash) {
    Write-Host 'Updating application dependencies...'
    & $venvPython -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Dependency update failed. Run Start.cmd again to retry.' }
    Set-Content -LiteralPath $hashMarker -Value $requirementsHash
}
& $venvPython (Join-Path $releasePath 'app.py')
if ($LASTEXITCODE -ne 0) { throw 'Application stopped with an error. Read the message above.' }
