$ErrorActionPreference = "SilentlyContinue"
$InstallDir = Join-Path $env:LOCALAPPDATA "StockTrackRunner"

Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like "*StockTrackRunner*runner.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Startup")) "StockTrackRunner.lnk"
if (Test-Path $ShortcutPath) { Remove-Item $ShortcutPath -Force }

$answer = Read-Host "Ayar ve gunluk dosyalari da silinsin mi? (e/h)"
if ($answer -eq "e") {
    Remove-Item $InstallDir -Recurse -Force
    Write-Host "Silindi: $InstallDir"
} else {
    Get-ChildItem $InstallDir -Filter *.py | Remove-Item -Force
    Write-Host "Program kaldirildi; ayarlar korundu: $InstallDir"
}
Write-Host "Acilmis klasorlere dokunulmadi."
