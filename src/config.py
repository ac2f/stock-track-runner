import json
import os
import threading

from addon import addon_settings

# Eski kurulumlarin config.json'inda kalan ornek adres: bos sayilir.
PLACEHOLDER_SERVER = "http://192.168.1.50/api/v1"

DEFAULT_CONFIG = {
    "enabled": True,
    # Bos birakilirsa Corel eklentisindeki adres ve anahtar kullanilir.
    "server": "",
    "api_key": "",
    "poll_seconds": 30,
    "day_folders": {
        "base_dir": "",
        "renamer_config": "%LOCALAPPDATA%\\CdrAutoRenamer\\config.json",
        "date_format": "%d-%m-%Y",
        "separator": "--"
    },
    # Bos/null: Corel eklentisinin ayari, o da yoksa "--" ve 4000.
    "group_separator": "",
    "long_sheet_mm": None,
    "open_explorer": False,
    "log_file": "runner.log"
}


def _merge(base, extra):
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    """JSON ayar dosyasi; diskte degisince kendiliginden yeniden okunur
    (runner'i yeniden baslatmaya gerek yok). Bos alanlar Corel eklentisinin
    ayarlarindan, gun klasoru en son CDR Auto Renamer'dan tamamlanir."""

    def __init__(self, path, addon_reader=None):
        self.path = path
        self._lock = threading.Lock()
        self._mtime = None
        self._addon_reader = addon_reader
        self.data = json.loads(json.dumps(DEFAULT_CONFIG))
        self.load(create_if_missing=True)

    def load(self, create_if_missing=False):
        with self._lock:
            if not os.path.exists(self.path):
                if create_if_missing:
                    with open(self.path, "w", encoding="utf-8") as f:
                        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
                    self._mtime = os.path.getmtime(self.path)
                return
            with open(self.path, "r", encoding="utf-8-sig") as f:
                self.data = _merge(DEFAULT_CONFIG, json.load(f))
            self._mtime = os.path.getmtime(self.path)

    def reload_if_changed(self):
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if self._mtime is None or mtime > self._mtime:
            self.load()

    def __getitem__(self, key):
        return self.data.get(key, DEFAULT_CONFIG.get(key))

    def addon(self):
        """Corel eklentisinin ayarlari (her cagrida taze okunur)."""
        return addon_settings(self._addon_reader)

    def connection(self):
        """(sunucu, anahtar, kaynak). config.json'daki deger once gelir;
        bossa Corel eklentisinin kayitli adresi ve anahtari."""
        server = (self["server"] or "").strip().rstrip("/")
        key = (self["api_key"] or "").strip()
        addon = self.addon()
        source = "runner config.json"
        if not key and addon.get("api_key"):
            key = addon["api_key"]
            source = "Corel eklentisi"
        if (not server or server == PLACEHOLDER_SERVER) and addon.get("server"):
            server = addon["server"]
            source = "Corel eklentisi"
        return server, key, source

    def group_separator(self):
        return self["group_separator"] or self.addon().get("separator") or "--"

    def long_sheet_mm(self):
        value = self["long_sheet_mm"]
        if value is None or value == "":
            value = self.addon().get("long_mm", 4000)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 4000.0

    def day_rule(self):
        """Gun klasoru kurali; Corel eklentisiyle ayni oncelik:
          1) config.json'daki day_folders.base_dir,
          2) Corel eklentisinin "gun klasoru koku" ayari,
          3) CDR Auto Renamer'in config.json'u (daily_folders).
        1'de tarih bicimi ve ayrac config.json'dan, 2-3'te CDR Auto Renamer'dan.
        Bulunamazsa None. `warning`: dikkat edilmesi gereken durum."""
        own = self["day_folders"] or {}
        rule = {
            "base_dir": (own.get("base_dir") or "").strip(),
            "date_format": own.get("date_format") or "%d-%m-%Y",
            "separator": own.get("separator") if own.get("separator") is not None else "--",
            "source": "runner config.json",
            "warning": "",
        }
        daily = None
        rc = os.path.expandvars(own.get("renamer_config") or "")
        try:
            with open(rc, "r", encoding="utf-8-sig") as f:
                daily = json.load(f).get("daily_folders") or {}
        except (OSError, ValueError):
            daily = None
        if rule["base_dir"]:
            return rule
        # Kok eklentiden ya da CDR Auto Renamer'dan geliyorsa gun klasoru adi
        # CDR Auto Renamer'in bicimiyle (eklenti de oyle yapar).
        if daily is not None:
            rule["date_format"] = daily.get("date_format") or rule["date_format"]
            if daily.get("separator") is not None:
                rule["separator"] = daily["separator"]
        addon_root = self.addon().get("day_root")
        if addon_root:
            rule["base_dir"] = addon_root.rstrip("\\/") or addon_root
            rule["source"] = "Corel eklentisi"
            return rule
        if daily and daily.get("base_dir"):
            rule["base_dir"] = daily["base_dir"]
            rule["source"] = "CDR Auto Renamer"
            if not daily.get("enabled"):
                rule["warning"] = ("CDR Auto Renamer'da gunluk klasorler kapali; yine de onun "
                                   "ayarindaki kok kullaniliyor. Dogru yer degilse Corel eklentisinde "
                                   "ya da config.json'da gun klasoru kokunu yazin.")
            return rule
        return None
