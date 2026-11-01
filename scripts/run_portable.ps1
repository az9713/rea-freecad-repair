param([string]$Script = 'tests/integration_freecad.py', [switch]$Gui)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Portfolio = Split-Path -Parent (Split-Path -Parent $ProjectRoot)
$SharedEnvironment = Join-Path $Portfolio 'portfolio/env.ps1'
if (Test-Path -LiteralPath $SharedEnvironment) { . $SharedEnvironment }
Set-Location -LiteralPath $ProjectRoot
# Every known user/config/cache location is redirected before launching Qt/FreeCAD.
$PrivateHome = Join-Path $ProjectRoot '.runtime/home'
$env:HOME = $PrivateHome
$env:USERPROFILE = $PrivateHome
$env:APPDATA = Join-Path $PrivateHome 'AppData/Roaming'
$env:LOCALAPPDATA = Join-Path $PrivateHome 'AppData/Local'
$env:XDG_CONFIG_HOME = Join-Path $PrivateHome '.config'
$env:XDG_CACHE_HOME = Join-Path $PrivateHome '.cache'
$env:XDG_DATA_HOME = Join-Path $PrivateHome '.local/share'
$env:FREECAD_USER_HOME = Join-Path $PrivateHome 'FreeCAD'
$env:TEMP = Join-Path $ProjectRoot '.runtime/tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $ProjectRoot '.runtime/pycache'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QTWEBENGINE_DISABLE_SANDBOX = '1'
$env:TOPOINTENT_ROOT = $ProjectRoot
New-Item -ItemType Directory -Force -Path $env:HOME,$env:APPDATA,$env:LOCALAPPDATA,$env:XDG_CONFIG_HOME,$env:XDG_CACHE_HOME,$env:XDG_DATA_HOME,$env:FREECAD_USER_HOME,$env:TEMP | Out-Null
$ApplicationName = if ($Gui) { 'FreeCAD.exe' } else { 'FreeCADCmd.exe' }
$Application = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot '.runtime/freecad') -Recurse -Filter $ApplicationName | Select-Object -First 1
if (-not $Application) { throw 'Run scripts/acquire_freecad.py before this launcher' }
$UserConfig = Join-Path $env:FREECAD_USER_HOME 'user.cfg'
$SystemConfig = Join-Path $env:FREECAD_USER_HOME 'system.cfg'
if ($Script -eq '--help') {
    & $Application.FullName --user-cfg $UserConfig --system-cfg $SystemConfig --help
} else {
    $ResolvedScript = (Resolve-Path -LiteralPath $Script).Path
    if (-not $ResolvedScript.StartsWith($ProjectRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Script must stay inside project' }
    if ($Script -eq 'tests/integration_freecad.py') {
        $Report = Join-Path $ProjectRoot 'artifacts/integration-results.json'
        if (Test-Path -LiteralPath $Report) { Remove-Item -LiteralPath $Report }
    }
    if ($Gui -and $Script -eq 'tests/gui_smoke.FCMacro') {
        $GuiReport = Join-Path $ProjectRoot 'artifacts/gui-results.json'
        if (Test-Path -LiteralPath $GuiReport) { Remove-Item -LiteralPath $GuiReport }
    }
    & $Application.FullName --user-cfg $UserConfig --system-cfg $SystemConfig $ResolvedScript
}
if ($LASTEXITCODE) { throw "FreeCAD exited with $LASTEXITCODE" }
if ($Script -eq 'tests/integration_freecad.py') {
    if (-not (Test-Path -LiteralPath $Report)) { throw 'FreeCAD did not produce a native integration report' }
    $Result = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
    if ($Result.passed -ne $Result.total -or $Result.total -lt 7) { throw 'Native integration report contains failures' }
}
if ($Gui -and $Script -eq 'tests/gui_smoke.FCMacro') {
    $Deadline = (Get-Date).AddSeconds(60)
    while (-not (Test-Path -LiteralPath $GuiReport) -and (Get-Date) -lt $Deadline) { Start-Sleep -Milliseconds 200 }
    if (-not (Test-Path -LiteralPath $GuiReport)) { throw 'FreeCAD GUI did not produce a smoke report within 60 seconds' }
    $Result = Get-Content -LiteralPath $GuiReport -Raw | ConvertFrom-Json
    if ($Result.errors.Count -gt 0 -or $Result.passed -lt 4) { throw 'Native GUI report contains failures' }
    Write-Output "Native GUI checks passed: $($Result.passed)"
}
