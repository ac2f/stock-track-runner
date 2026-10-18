import json
import os
import threading

DEFAULT_CONFIG = {
    "enabled": True,
    "server": "http://192.168.1.50/api/v1",
    "api_key": "",
    "poll_seconds": 30,
    "day_folders": {
        "base_dir": "",
        "renamer_config": "%LOCALAPPDATA%\\CdrAutoRenamer\\config.json",
        "date_format": "%d-%m-%Y",
        "separator": "--"
    },
    "group_separator": "--",
    "long_sheet_mm": 4000,
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
    (runner'i yeniden baslatmaya gerek yok)."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._mtime = None
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

    def day_rule(self):
        """Gun klasoru kurali: base_dir doluysa bu dosyadan, bossa CDR Auto
        Renamer'in config.json'undan (ana dizin, tarih bicimi, ayrac). Iki
        program ayni klasoru kullanir, ikinci bir ayar gerekmez.
        Bulunamazsa None."""
        own = self["day_folders"] or {}
        rule = {
            "base_dir": (own.get("base_dir") or "").strip(),
            "date_format": own.get("date_format") or "%d-%m-%Y",
            "separator": own.get("separator") if own.get("separator") is not None else "--",
            "source": "runner config.json",
        }
        if rule["base_dir"]:
            return rule
        rc = os.path.expandvars(own.get("renamer_config") or "")
        try:
            with open(rc, "r", encoding="utf-8-sig") as f:
                daily = json.load(f).get("daily_folders") or {}
        except (OSError, ValueError):
            return None
        if not daily.get("base_dir"):
            return None
        return {
            "base_dir": daily["base_dir"],
            "date_format": daily.get("date_format") or "%d-%m-%Y",
            "separator": daily.get("separator") if daily.get("separator") is not None else "--",
            "source": rc,
        }
