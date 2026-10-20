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
Copy-Item -Path (Join-Path $ScriptDir "src\*.pyw") -Destination $InstallDir -Force

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python bulunamadi. Once https://www.python.org/downloads/ adresinden Python 3 kurun (kurulumda 'Add python.exe to PATH' kutusunu isaretleyin), sonra bu kurulumu tekrar calistirin."
    exit 1
}
$PythonExe = (& python -c "import sys; print(sys.executable)").Trim()
$Pythonw = Join-Path (Split-Path -Parent $PythonExe) "pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = $PythonExe }

# Corel eklentisinin (ac2f pack) kayitli ayarlari: adres ve anahtar oradaysa
# sorulmaz, runner her zaman eklentidekini kullanir.
$AddonKey = "HKCU:\Software\VB and VBA Program Settings\ac2fPack\Ayarlar"
$AddonServer = ""
$AddonApiKey = ""
if (Test-Path $AddonKey) {
    $props = Get-ItemProperty -Path $AddonKey -ErrorAction SilentlyContinue
    if ($props.JBSunucuAdresi) { $AddonServer = "$($props.JBSunucuAdresi)".Trim() }
    if ($props.JBAnahtar) { $AddonApiKey = "$($props.JBAnahtar)".Trim() }
}

$ConfigPath = Join-Path $InstallDir "config.json"
if (-not (Test-Path $ConfigPath)) {
    $cfg = Get-Content (Join-Path $ScriptDir "config.example.json") -Raw | ConvertFrom-Json
    Write-Host ""
    if ($AddonServer -and $AddonApiKey) {
        Write-Host "Corel eklentisindeki baglanti bulundu: $AddonServer"
        Write-Host "Runner bu adresi ve anahtari kullanacak (eklentide degistirirseniz runner da izler)."
    } else {
        Write-Host "StockTrack > Ayarlar > Corel entegrasyonu sayfasindaki bilgileri girin."
        Write-Host "(Corel eklentisine girdiginiz adres ve anahtarin aynisi.)"
        $server = Read-Host "Sunucu adresi (ornek http://192.168.1.50/api/v1)"
        if ($server) { $cfg.server = $server.Trim().TrimEnd('/') }
        $key = Read-Host "Corel anahtari"
        if ($key) { $cfg.api_key = $key.Trim() }
    }
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

$WshShell = New-Object -ComObject WScript.Shell
function New-Shortcut($Path, $Target, $Arguments, $Description) {
    $s = $WshShell.CreateShortcut($Path)
    $s.TargetPath = $Target
    $s.Arguments = $Arguments
    $s.WorkingDirectory = $InstallDir
    $s.Description = $Description
    $s.Save()
}

$AppPath = Join-Path $InstallDir "runner.py"
$StatusPath = Join-Path $InstallDir "status.pyw"
$StartupLink = Join-Path ([Environment]::GetFolderPath("Startup")) "StockTrackRunner.lnk"
New-Shortcut $StartupLink $Pythonw ('"' + $AppPath + '"') "StockTrack Runner - ise donusen teklifler icin klasor acar"
Write-Host "Windows acilisinda calisma kisayolu: $StartupLink"

# Durum penceresi: masaustu ve Baslat menusu.
$DesktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "StockTrack Runner Durumu.lnk"
$MenuLink = Join-Path ([Environment]::GetFolderPath("Programs")) "StockTrack Runner Durumu.lnk"
foreach ($link in @($DesktopLink, $MenuLink)) {
    New-Shortcut $link $Pythonw ('"' + $StatusPath + '"') "StockTrack Runner calisiyor mu, bagli mi, son acilan klasorler"
}
Write-Host "Durum penceresi kisayolu: masaustunde 'StockTrack Runner Durumu'"

Start-Process -FilePath $Pythonw -ArgumentList ('"' + $AppPath + '"') -WorkingDirectory $InstallDir
Write-Host ""
Write-Host "Runner baslatildi; ilk turu bekleniyor..."
Start-Sleep -Seconds 8
& $PythonExe $AppPath --status
Write-Host ""
Write-Host "Kurulum tamamlandi."
Write-Host "Klasorler teklif StockTrack'te ISE DONUSTURULUNCE acilir (teklif olusturulunca degil)."
Write-Host "Durumu her zaman masaustundeki 'StockTrack Runner Durumu' ile ya da StockTrack > Ayarlar > Corel entegrasyonu'ndan gorebilirsiniz."
Start-Process -FilePath $Pythonw -ArgumentList ('"' + $StatusPath + '"') -WorkingDirectory $InstallDir
