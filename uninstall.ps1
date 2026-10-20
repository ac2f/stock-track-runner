$ErrorActionPreference = "SilentlyContinue"
$InstallDir = Join-Path $env:LOCALAPPDATA "StockTrackRunner"

Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like "*StockTrackRunner*runner.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$Links = @(
    (Join-Path ([Environment]::GetFolderPath("Startup")) "StockTrackRunner.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "StockTrack Runner Durumu.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "StockTrack Runner Durumu.lnk")
)
foreach ($link in $Links) { if (Test-Path $link) { Remove-Item $link -Force } }

$answer = Read-Host "Ayar ve gunluk dosyalari da silinsin mi? (e/h)"
if ($answer -eq "e") {
    Remove-Item $InstallDir -Recurse -Force
    Write-Host "Silindi: $InstallDir"
} else {
    Get-ChildItem $InstallDir -Include *.py, *.pyw -Recurse | Remove-Item -Force
    Write-Host "Program kaldirildi; ayarlar korundu: $InstallDir"
}
Write-Host "Acilmis klasorlere dokunulmadi."
