"""Runner'in anlik durumu: status.json.

Runner her turda yazar; durum penceresi (status.pyw) ve `runner.py --status`
okur. Calisiyor mu sorusunun cevabi tek basina bu dosya degildir (runner
kapanirken dosya kalir): son turun zamani ve tekil-calisma kilidi birlikte
bakilir.
"""
import datetime
import json
import os

RECENT_MAX = 15


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def read_status(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_status(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass


def add_recent(status, item):
    recent = [r for r in status.get("recent") or [] if r.get("quoteId") != item.get("quoteId")]
    status["recent"] = [item] + recent[: RECENT_MAX - 1]


def seconds_since(iso):
    if not iso:
        return None
    try:
        t = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.astimezone()
    return max(0, int((datetime.datetime.now().astimezone() - t).total_seconds()))


def ago(seconds):
    if seconds is None:
        return "hic"
    if seconds < 60:
        return "%d sn once" % seconds
    if seconds < 3600:
        return "%d dk once" % (seconds // 60)
    if seconds < 86400:
        return "%d saat once" % (seconds // 3600)
    return "%d gun once" % (seconds // 86400)


def is_fresh(status, running_lock):
    """Runner calisiyor mu: kilit tutuluyor ve son tur beklenen surede."""
    if not running_lock:
        return False
    since = seconds_since(status.get("lastLoopAt"))
    poll = int(status.get("pollSeconds") or 30)
    return since is not None and since <= poll * 3 + 15


def describe(status, running_lock):
    """Okunur satirlar (konsol ve pencere icin)."""
    lines = []
    if is_fresh(status, running_lock):
        lines.append("Durum:        CALISIYOR (son tur %s)" % ago(seconds_since(status.get("lastLoopAt"))))
    elif running_lock:
        lines.append("Durum:        CALISIYOR ama son tur gecikti (%s)" % ago(seconds_since(status.get("lastLoopAt"))))
    else:
        lines.append("Durum:        CALISMIYOR")
    if status.get("server"):
        conn = "baglandi" if status.get("connected") else "baglanamadi"
        shop = " - %s" % status["shopName"] if status.get("shopName") else ""
        lines.append("Sunucu:       %s  (%s%s; kaynak: %s)" % (status["server"], conn, shop, status.get("serverSource", "?")))
    if status.get("dayRoot"):
        lines.append("Gun klasoru:  %s  (kaynak: %s)" % (status["dayRoot"], status.get("dayRootSource", "?")))
    if status.get("today"):
        lines.append("Bugun:        %s" % status["today"])
    if status.get("dayRootWarning"):
        lines.append("Uyari:        %s" % status["dayRootWarning"])
    lines.append("Son hata:     %s" % (status.get("error") or "yok"))
    recent = status.get("recent") or []
    if recent:
        lines.append("Son acilan klasorler:")
        for r in recent[:5]:
            lines.append("  %s  %s  %s" % (r.get("quoteNo", "?"), (r.get("at") or "")[:16].replace("T", " "), r.get("folder", "")))
    else:
        lines.append("Son acilan klasorler: henuz yok (klasorler teklif ISE DONUSTURULUNCE acilir)")
    return lines
