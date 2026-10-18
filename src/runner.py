"""StockTrack Runner: teklif ise donusturulunce dukkan bilgisayarinda
klasorleri acar.

StockTrack'te bir teklif "Satis/Islemeye Donustur" ile ise donunce, runner
birkac saniye icinde (poll_seconds) bunu gorur ve gunun klasorunde:
  - musteri klasorunu (ozturk-reklam-ltd-sti),
  - teklifteki tabakalarin takim yolu klasorlerini (istifleyerek, uzun
    tabakada p001/p002 ile),
  - tabakanin bir kismi kullanildiysa u1220x900 dosyasini
acar. Klasor adlari Corel eklentisiyle (ac2fJob) aynidir.

Calistirma:
  pythonw runner.py          arka planda (Windows acilisinda kisayolla)
  python runner.py --check   ayarlari ve sunucu baglantisini dener
  python runner.py --once    bekleyenleri bir kez isler ve cikar
"""
import argparse
import datetime
import json
import logging
import os
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler

from config import Config
from folders import already_done, customer_dir, make_groups, plan_groups, write_marker
from stocktrack import ServerError, StockTrack

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
PAGE = 50
KEEP_DONE_DAYS = 3

logger = logging.getLogger("stocktrack_runner")


def setup_logger(log_file, console=False):
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(os.path.join(BASE_DIR, log_file), maxBytes=1_000_000,
                             backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    if console:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)


def parse_time(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))


def local_date(iso):
    return parse_time(iso).astimezone().date()


class State:
    """Nereye kadar bakildigi (cursor) ve islenen tekliflerin kimlikleri.
    Ayni teklif iki kez islenmez; asil guvence musteri klasorundeki
    isarettir (.stocktrack), ayni klasoru paylasan iki bilgisayar icin de."""

    def __init__(self, path):
        self.path = path
        self.cursor = None
        self.done = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.cursor = data.get("cursor")
            self.done = data.get("done") or {}
        except (OSError, ValueError):
            pass

    def save(self):
        if self.cursor:
            limit = parse_time(self.cursor) - datetime.timedelta(days=KEEP_DONE_DAYS)
            self.done = {k: v for k, v in self.done.items() if parse_time(v) >= limit}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cursor": self.cursor, "done": self.done}, f, indent=2)
        os.replace(tmp, self.path)


def start_of_today_iso():
    """Ilk calistirmada bugunun basindan baslanir: gecmisteki butun donusmus
    teklifler icin klasor acilmaz, bugunkuler kacmaz."""
    now = datetime.datetime.now().astimezone()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc).isoformat()


def process_job(job, cfg, rule):
    """Bir teklifin klasorlerini acar. (musteri klasoru, yapilanlar)."""
    root = rule["base_dir"]
    cdir = customer_dir(root, rule, job["customerFolder"],
                        local_date(job["createdAt"]), local_date(job["convertedAt"]))
    if already_done(cdir, job["id"]):
        return cdir, ["zaten acilmis (isaret var)"]
    plan = plan_groups(job.get("sheets") or [])
    header = "Quote %s  %s\n" % (job["quoteNo"], local_date(job["createdAt"]).isoformat())
    report, problems = make_groups(cdir, plan, cfg["group_separator"] or "--",
                                   float(cfg["long_sheet_mm"] or 0), header)
    if not plan:
        report.append("tabaka kalemi yok, yalniz musteri klasoru")
    write_marker(cdir, job, report + problems)
    for p in problems:
        logger.warning("%s: %s", job["quoteNo"], p)
    return cdir, report


def poll_once(cfg, state, api):
    """Bekleyen donusumleri isler; islenen sayisi. Sunucu ya da klasor
    hatasinda durur, sira bozulmasin diye kalanlar bir sonraki tura kalir."""
    rule = cfg.day_rule()
    if not rule:
        logger.error("Gun klasoru bilinmiyor: CDR Auto Renamer'da gunluk klasorleri acin "
                     "ya da config.json'da day_folders.base_dir yazin.")
        return 0
    if not state.cursor:
        state.cursor = start_of_today_iso()
        state.save()
    count = 0
    while True:
        jobs = api.jobs(state.cursor, PAGE)
        fresh = [j for j in jobs if j["id"] not in state.done]
        for job in fresh:
            try:
                cdir, report = process_job(job, cfg, rule)
            except OSError as exc:
                logger.error("%s icin klasor acilamadi: %s (bir sonraki turda yeniden)", job["quoteNo"], exc)
                return count
            logger.info("%s -> %s\n    %s", job["quoteNo"], cdir, "\n    ".join(report))
            state.done[job["id"]] = job["convertedAt"]
            state.cursor = max(state.cursor, job["convertedAt"], key=parse_time)
            state.save()
            count += 1
            if cfg["open_explorer"] and os.name == "nt":
                subprocess.Popen(["explorer.exe", cdir])
        # sayfa doluysa ve hepsi zaten islenmisse (ayni ana dusen cok teklif)
        # sonraki sayfa icin cursor'i bir milisaniye ileri al
        if len(jobs) < PAGE:
            return count
        if not fresh:
            nxt = parse_time(state.cursor) + datetime.timedelta(milliseconds=1)
            state.cursor = nxt.isoformat()


def single_instance():
    """Ayni bilgisayarda ikinci runner calismasin (acilis + elle baslatma)."""
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\StockTrackRunner")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return None
        return handle
    import fcntl
    f = open(os.path.join(BASE_DIR, ".lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return f


def check(cfg):
    print("Ayar dosyasi:  %s" % CONFIG_PATH)
    rule = cfg.day_rule()
    if rule:
        today = datetime.date.today()
        from folders import day_folder_name, find_day_dir
        d = find_day_dir(rule["base_dir"], today, rule["date_format"], rule["separator"])
        print("Gun klasoru:   %s  (%s)" % (rule["base_dir"], rule["source"]))
        path = d or os.path.join(rule["base_dir"], day_folder_name(today, rule["date_format"], rule["separator"]))
        print("Bugun:         %s%s" % (path, "" if d else "  (henuz yok, ilk iste acilir)"))
    else:
        print("Gun klasoru:   BILINMIYOR - CDR Auto Renamer'da gunluk klasorleri acin ya da")
        print("               config.json'da day_folders.base_dir yazin.")
    if not cfg["api_key"]:
        print("Anahtar:       YOK - StockTrack > Ayarlar > Corel entegrasyonu'ndaki anahtari")
        print("               config.json'da api_key'e yazin.")
        return 1
    try:
        name = StockTrack(cfg["server"], cfg["api_key"]).ping()
        print("Sunucu:        %s  -> baglandi: %s" % (cfg["server"], name))
    except ServerError as exc:
        print("Sunucu:        %s  -> %s" % (cfg["server"], exc))
        return 1
    return 0 if rule else 1


def main():
    ap = argparse.ArgumentParser(description="StockTrack Runner")
    ap.add_argument("--check", action="store_true", help="ayarlari ve baglantiyi dene")
    ap.add_argument("--once", action="store_true", help="bekleyenleri bir kez isle ve cik")
    args = ap.parse_args()

    cfg = Config(CONFIG_PATH)
    if args.check:
        sys.exit(check(cfg))

    setup_logger(cfg["log_file"], console=args.once)
    lock = single_instance()
    if lock is None:
        logger.info("Runner zaten calisiyor; bu kopya kapaniyor.")
        if args.once:
            print("Runner zaten calisiyor.")
        return
    state = State(STATE_PATH)
    logger.info("StockTrack Runner basliyor (%s)", cfg["server"])

    last_error = None
    while True:
        cfg.reload_if_changed()
        if cfg["enabled"] and cfg["api_key"]:
            try:
                api = StockTrack(cfg["server"], cfg["api_key"])
                n = poll_once(cfg, state, api)
                if n:
                    logger.info("%d teklif icin klasorler acildi", n)
                if last_error:
                    logger.info("Sunucuya yeniden ulasildi")
                last_error = None
            except ServerError as exc:
                # ayni hatayi her turda tekrar yazma
                if str(exc) != last_error:
                    logger.warning("%s", exc)
                last_error = str(exc)
        elif not cfg["api_key"] and last_error != "nokey":
            logger.warning("config.json'da api_key bos: StockTrack > Ayarlar > Corel entegrasyonu")
            last_error = "nokey"
        if args.once:
            return
        time.sleep(max(5, int(cfg["poll_seconds"] or 30)))


if __name__ == "__main__":
    main()
