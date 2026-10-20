"""Corel eklentisinin (ac2f pack, ac2fJob) ayarlari.

Eklenti ayarlarini Windows kayit defterine yazar (VBA SaveSetting):
  HKCU\\Software\\VB and VBA Program Settings\\ac2fPack\\Ayarlar
Runner ayni sunucu adresini, anahtari ve gun klasoru kokunu buradan okur;
boylece ikisi her zaman ayni yere bakar ve kurulumda bir sey yazmak gerekmez.
Windows disinda (ve eklenti hic kurulmamissa) bos doner.
"""
import os

REG_PATH = r"Software\VB and VBA Program Settings\ac2fPack\Ayarlar"

# runner adi -> eklentinin kayit adi (ac2fJob.bas, AC2F_K_JB_*)
KEYS = {
    "server": "JBSunucuAdresi",
    "api_key": "JBAnahtar",
    "day_root": "JBGunlukKlasorKoku",
    "separator": "JBAyrac",
    "long_mm": "JBUzunPlakaMM",
}


def _read_registry():
    if os.name != "nt":
        return {}
    import winreg
    out = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    except OSError:
        return {}
    try:
        for name, reg in KEYS.items():
            try:
                value, _ = winreg.QueryValueEx(key, reg)
            except OSError:
                continue
            value = str(value).strip()
            if value:
                out[name] = value
    finally:
        winreg.CloseKey(key)
    return out


def addon_settings(reader=None):
    """Eklentinin dolu ayarlari: server, api_key, day_root, separator, long_mm."""
    data = (reader or _read_registry)()
    if "server" in data:
        data["server"] = data["server"].rstrip("/")
    if "long_mm" in data:
        try:
            data["long_mm"] = float(data["long_mm"].replace(",", "."))
        except ValueError:
            del data["long_mm"]
    return data
