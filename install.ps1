$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Join-Path $env:LOCALAPPDATA "StockTrackRunner"

Write-Host "StockTrack Runner kuruluyor -> $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# Calisiyorsa once durdur (dosyalar degisecek).
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*StockTrackRunner*runner.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Copy-Item -Path (Join-Path $ScriptDir "src\*.py") -Destination $InstallDir -Force

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python bulunamadi. Once https://www.python.org/downloads/ adresinden Python 3 kurun (kurulumda 'Add python.exe to PATH' kutusunu isaretleyin), sonra bu kurulumu tekrar calistirin."
    exit 1
}
$PythonExe = (& python -c "import sys; print(sys.executable)").Trim()
$Pythonw = Join-Path (Split-Path -Parent $PythonExe) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = $PythonExe }

$ConfigPath = Join-Path $InstallDir "config.json"
if (-not (Test-Path $ConfigPath)) {
    $cfg = Get-Content (Join-Path $ScriptDir "config.example.json") -Raw | ConvertFrom-Json
    Write-Host ""
    Write-Host "StockTrack > Ayarlar > Corel entegrasyonu sayfasindaki bilgileri girin."
    Write-Host "(Corel eklentisine girdiginiz adres ve anahtarin aynisi.)"
    $server = Read-Host "Sunucu adresi (ornek http://192.168.1.50/api/v1)"
    if ($server) { $cfg.server = $server.Trim().TrimEnd('/') }
    $key = Read-Host "Corel anahtari"
    if ($key) { $cfg.api_key = $key.Trim() }
    $json = $cfg | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($ConfigPath, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Ayar dosyasi olusturuldu: $ConfigPath"
} else {
    Write-Host "Mevcut ayar dosyasi korundu: $ConfigPath"
}

Write-Host ""
Write-Host "Baglanti deneniyor..."
& $PythonExe (Join-Path $InstallDir "runner.py") --check
Write-Host ""

$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "StockTrackRunner.lnk"
$AppPath = Join-Path $InstallDir "runner.py"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Pythonw
$Shortcut.Arguments = '"' + $AppPath + '"'
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "StockTrack Runner - ise donusen teklifler icin klasor acar"
$Shortcut.Save()
Write-Host "Windows acilisinda calisma kisayolu olusturuldu: $ShortcutPath"

Start-Process -FilePath $Pythonw -ArgumentList ('"' + $AppPath + '"') -WorkingDirectory $InstallDir
Write-Host ""
Write-Host "Kurulum tamamlandi; runner arka planda calisiyor."
Write-Host "Ayarlar: $ConfigPath"
Write-Host "Gunluk:  $(Join-Path $InstallDir 'runner.log')"
