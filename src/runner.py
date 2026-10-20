"""StockTrack Runner: teklif ise donusturulunce dukkan bilgisayarinda
klasorleri acar.

StockTrack'te bir teklif "Satis/Islemeye Donustur" ile ise donunce, runner
birkac saniye icinde (poll_seconds) bunu gorur ve gunun klasorunde:
  - musteri klasorunu (ozturk-reklam-ltd-sti),
  - teklifteki tabakalarin takim yolu klasorlerini (istifleyerek, uzun
    tabakada p001/p002 ile),
  - tabakanin bir kismi kullanildiysa u1220x900 dosyasini
acar. Klasor adlari Corel eklentisiyle (ac2fJob) aynidir.

Her turda StockTrack'e nabiz gonderir (Ayarlar > Corel entegrasyonu'nda
"runner bagli" gorunur), actigi klasoru teklife bildirir ve durumunu
status.json'a yazar (durum penceresi: status.pyw).

Calistirma:
  pythonw runner.py          arka planda (Windows acilisinda kisayolla)
  python runner.py --check   ayarlari ve sunucu baglantisini dener
  python runner.py --status  calisiyor mu, son klasorler, son hata
  python runner.py --once    bekleyenleri bir kez isler ve cikar
"""
import argparse
import datetime
import json
import logging
import os
import socket
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler

from config import Config
from folders import EMPTY_NOTE, already_done, customer_dir, marker_was_empty, day_folder_name, find_day_dir, make_groups, plan_groups, write_marker
from status import add_recent, describe, now_iso, read_status, write_status
from stocktrack import ServerError, StockTrack

VERSION = "1.1.1"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
STATUS_PATH = os.path.join(BASE_DIR, "status.json")
# Durum penceresindeki "Simdi bak" bu dosyayi birakir; runner beklemeyi keser.
POKE_PATH = os.path.join(BASE_DIR, "poll.now")
LOCK_PATH = os.path.join(BASE_DIR, ".lock")
MUTEX_NAME = "Global\\StockTrackRunner"
PAGE = 50
KEEP_DONE_DAYS = 3
PING_EVERY_SECONDS = 600
HOST = (os.environ.get("COMPUTERNAME") or socket.gethostname() or "bilgisayar")[:120]

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
    """Nereye kadar bakildigi (cursor), islenen tekliflerin kimlikleri ve
    sunucuya henuz bildirilemeyen klasorler. Ayni teklif iki kez islenmez;
    asil guvence musteri klasorundeki isarettir (.stocktrack), ayni klasoru
    paylasan iki bilgisayar icin de."""

    def __init__(self, path):
        self.path = path
        self.cursor = None
        self.done = {}
        self.unreported = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.cursor = data.get("cursor")
            self.done = data.get("done") or {}
            self.unreported = data.get("unreported") or {}
        except (OSError, ValueError):
            pass

    def save(self):
        if self.cursor:
            limit = parse_time(self.cursor) - datetime.timedelta(days=KEEP_DONE_DAYS)
            self.done = {k: v for k, v in self.done.items() if parse_time(v) >= limit}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cursor": self.cursor, "done": self.done, "unreported": self.unreported}, f, indent=2)
        os.replace(tmp, self.path)


def start_of_today_iso():
    """Ilk calistirmada bugunun basindan baslanir: gecmisteki butun donusmus
    teklifler icin klasor acilmaz, bugunkuler kacmaz."""
    now = datetime.datetime.now().astimezone()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc).isoformat()


def process_job(job, cfg, rule, requested=False):
    """Bir teklifin klasorlerini acar. (musteri klasoru, yapilanlar, sorunlar).
    `requested`: StockTrack'ten yeniden istendi; isaret varsa yine atlanir,
    yalniz o tur hic tabaka acilmamis ve simdi tabaka varsa yeniden acilir."""
    root = rule["base_dir"]
    cdir = customer_dir(root, rule, job["customerFolder"],
                        local_date(job["createdAt"]), local_date(job["convertedAt"]))
    plan = plan_groups(job.get("sheets") or [])
    if already_done(cdir, job["id"]):
        if not (requested and plan and marker_was_empty(cdir, job["id"])):
            return cdir, ["zaten acilmis (isaret var)"], []
    header = "Quote %s  %s\n" % (job["quoteNo"], local_date(job["createdAt"]).isoformat())
    report, problems = make_groups(cdir, plan, cfg.group_separator(), cfg.long_sheet_mm(), header)
    if not plan:
        report.append(EMPTY_NOTE)
    write_marker(cdir, job, report + problems)
    for p in problems:
        logger.warning("%s: %s", job["quoteNo"], p)
    return cdir, report, problems


def handle_job(job, cfg, rule, state, status=None, requested=False):
    """Klasorleri acar, bildirilecekler listesine ve son islere ekler."""
    cdir, report, problems = process_job(job, cfg, rule, requested)
    logger.info("%s -> %s\n    %s", job["quoteNo"], cdir, "\n    ".join(report + problems))
    state.done[job["id"]] = job["convertedAt"]
    state.unreported[job["id"]] = {
        "host": HOST,
        "folder": cdir[:500],
        "report": [r[:500] for r in report[:50]],
        "problems": [p[:500] for p in problems[:20]],
        "at": now_iso(),
    }
    if status is not None:
        add_recent(status, {
            "quoteId": job["id"],
            "quoteNo": job["quoteNo"],
            "customer": job.get("customerLabel") or job.get("customerFolder"),
            "folder": cdir,
            "at": now_iso(),
            "note": "; ".join(problems) or ("; ".join(report[:1]) if report else ""),
        })
    if cfg["open_explorer"] and os.name == "nt":
        subprocess.Popen(["explorer.exe", cdir])
    return cdir


def poll_once(cfg, state, api, status=None, errors=None):
    """Bekleyen donusumleri isler; islenen sayisi. Sunucu ya da klasor
    hatasinda durur, sira bozulmasin diye kalanlar bir sonraki tura kalir."""
    rule = cfg.day_rule()
    if not rule:
        msg = ("Gun klasoru bilinmiyor: Corel eklentisinde ya da CDR Auto Renamer'da gun klasoru "
               "kokunu ayarlayin ya da config.json'da day_folders.base_dir yazin.")
        logger.error(msg)
        if errors is not None:
            errors.append(msg)
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
                handle_job(job, cfg, rule, state, status)
            except OSError as exc:
                msg = "%s icin klasor acilamadi: %s (bir sonraki turda yeniden)" % (job["quoteNo"], exc)
                logger.error(msg)
                if errors is not None:
                    errors.append(msg)
                return count
            state.cursor = max(state.cursor, job["convertedAt"], key=parse_time)
            state.save()
            count += 1
        # sayfa doluysa ve hepsi zaten islenmisse (ayni ana dusen cok teklif)
        # sonraki sayfa icin cursor'i bir milisaniye ileri al
        if len(jobs) < PAGE:
            return count
        if not fresh:
            nxt = parse_time(state.cursor) + datetime.timedelta(milliseconds=1)
            state.cursor = nxt.isoformat()


def poll_requested(cfg, state, api, status=None, errors=None):
    """StockTrack ekranindan "klasorleri yeniden iste" denen teklifler.
    Daha once islenmis olsa da bakilir; musteri klasorundeki isaret
    varsa ikinci kez istiflenmez, yalniz klasor yeniden bildirilir."""
    rule = cfg.day_rule()
    if not rule:
        return 0
    count = 0
    for job in api.requested_jobs():
        if job["id"] in state.unreported:
            continue  # acildi, bildirimi bekliyor
        try:
            handle_job(job, cfg, rule, state, status, requested=True)
        except OSError as exc:
            msg = "%s icin klasor acilamadi: %s" % (job["quoteNo"], exc)
            logger.error(msg)
            if errors is not None:
                errors.append(msg)
            break
        state.save()
        count += 1
    return count


def flush_reports(state, api):
    """Acilan klasorleri StockTrack'e bildirir; ulasilamazsa sonraki tura."""
    sent = 0
    limit = datetime.datetime.now().astimezone() - datetime.timedelta(days=KEEP_DONE_DAYS)
    for quote_id, payload in list(state.unreported.items()):
        try:
            if parse_time(payload.get("at") or now_iso()) < limit:
                del state.unreported[quote_id]
                continue
        except ValueError:
            pass
        body = {k: v for k, v in payload.items() if k != "at"}
        try:
            api.report_folders(quote_id, body)
        except ServerError as exc:
            if "HTTP 404" in str(exc) or "HTTP 400" in str(exc):
                # teklif silinmis ya da sunucu bu ucu bilmiyor: tekrar denemenin yararı yok
                logger.warning("klasor bildirilemedi (%s): %s", quote_id, exc)
                del state.unreported[quote_id]
                continue
            raise
        del state.unreported[quote_id]
        sent += 1
    if sent:
        state.save()
    return sent


def lock_held():
    """Bu bilgisayarda bir runner calisiyor mu (tekil-calisma kilidi)."""
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, MUTEX_NAME)  # SYNCHRONIZE
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    import fcntl
    try:
        f = open(LOCK_PATH, "a")
    except OSError:
        return False
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return True
    fcntl.flock(f, fcntl.LOCK_UN)
    f.close()
    return False


def single_instance():
    """Ayni bilgisayarda ikinci runner calismasin (acilis + elle baslatma)."""
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return None
        return handle
    import fcntl
    f = open(LOCK_PATH, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return f


def today_path(rule):
    if not rule:
        return ""
    today = datetime.date.today()
    d = find_day_dir(rule["base_dir"], today, rule["date_format"], rule["separator"])
    return d or os.path.join(rule["base_dir"], day_folder_name(today, rule["date_format"], rule["separator"]))


def check(cfg):
    print("Runner %s, bilgisayar: %s" % (VERSION, HOST))
    print("Ayar dosyasi:  %s" % CONFIG_PATH)
    addon = cfg.addon()
    print("Corel eklentisi ayarlari: %s" % (", ".join(sorted(addon)) if addon else "bulunamadi"))
    rule = cfg.day_rule()
    ok = True
    if rule:
        today = datetime.date.today()
        d = find_day_dir(rule["base_dir"], today, rule["date_format"], rule["separator"])
        print("Gun klasoru:   %s  (kaynak: %s)" % (rule["base_dir"], rule["source"]))
        print("Bugun:         %s%s" % (today_path(rule), "" if d else "  (henuz yok, ilk iste acilir)"))
        if not os.path.isdir(rule["base_dir"]):
            print("               UYARI: bu klasor yok; ilk iste olusturulacak.")
        if rule.get("warning"):
            print("Uyari:         %s" % rule["warning"])
    else:
        ok = False
        print("Gun klasoru:   BILINMIYOR - Corel eklentisinde ya da CDR Auto Renamer'da gun klasoru")
        print("               kokunu ayarlayin ya da config.json'da day_folders.base_dir yazin.")
    server, key, source = cfg.connection()
    print("Sunucu:        %s  (kaynak: %s)" % (server or "YOK", source))
    if not key:
        print("Anahtar:       YOK - StockTrack > Ayarlar > Corel entegrasyonu'ndaki anahtari")
        print("               Corel eklentisine ya da config.json'da api_key'e yazin.")
        return 1
    api = StockTrack(server, key)
    try:
        print("Baglanti:      baglandi -> %s" % api.ping())
    except ServerError as exc:
        print("Baglanti:      %s" % exc)
        return 1
    try:
        api.jobs(start_of_today_iso(), 1)
        print("Is listesi:    tamam (sunucu runner'i destekliyor)")
    except ServerError as exc:
        print("Is listesi:    %s" % exc)
        ok = False
    running = lock_held()
    print("Calisiyor mu:  %s" % ("evet" if running else "HAYIR - Windows acilisinda baslar ya da durum penceresinden baslatin"))
    print("Hatirlatma:    klasorler teklif ISE DONUSTURULUNCE acilir (teklif olusturulunca degil).")
    return 0 if ok else 1


def print_status():
    for line in describe(read_status(STATUS_PATH), lock_held()):
        print(line)
    return 0


def wait(seconds):
    """poll_seconds kadar bekler; "Simdi bak" dosyasi gelirse hemen doner."""
    end = time.time() + seconds
    while time.time() < end:
        if os.path.exists(POKE_PATH):
            try:
                os.remove(POKE_PATH)
            except OSError:
                pass
            return
        time.sleep(1)


def main():
    ap = argparse.ArgumentParser(description="StockTrack Runner")
    ap.add_argument("--check", action="store_true", help="ayarlari ve baglantiyi dene")
    ap.add_argument("--status", action="store_true", help="calisiyor mu, son klasorler, son hata")
    ap.add_argument("--once", action="store_true", help="bekleyenleri bir kez isle ve cik")
    args = ap.parse_args()

    cfg = Config(CONFIG_PATH)
    if args.check:
        sys.exit(check(cfg))
    if args.status:
        sys.exit(print_status())

    setup_logger(cfg["log_file"], console=args.once)
    lock = single_instance()
    if lock is None:
        logger.info("Runner zaten calisiyor; bu kopya kapaniyor.")
        if args.once:
            print("Runner zaten calisiyor.")
        return
    state = State(STATE_PATH)
    status = read_status(STATUS_PATH)
    status.update({"version": VERSION, "pid": os.getpid(), "host": HOST, "startedAt": now_iso(),
                   "error": None, "connected": False})
    server, _key, source = cfg.connection()
    rule = cfg.day_rule()
    logger.info("StockTrack Runner %s basliyor: %s, sunucu %s (%s), gun klasoru %s (%s)",
                VERSION, HOST, server or "YOK", source,
                rule["base_dir"] if rule else "BILINMIYOR", rule["source"] if rule else "-")

    loop = Loop(cfg, state, status)
    while True:
        poll = loop.tick()
        if args.once:
            for line in describe(status, True):
                print(line)
            return
        wait(poll)


class Loop:
    """Bir tur: ayarlari tazele, isleri isle, bildir, nabiz gonder, durumu yaz."""

    def __init__(self, cfg, state, status, status_path=None):
        self.cfg = cfg
        self.state = state
        self.status = status
        self.status_path = status_path or STATUS_PATH
        self.last_error = None
        self.last_ping = 0.0

    def tick(self):
        cfg, state, status = self.cfg, self.state, self.status
        cfg.reload_if_changed()
        poll = max(5, int(cfg["poll_seconds"] or 30))
        server, key, source = cfg.connection()
        rule = cfg.day_rule()
        status.update({
            "pollSeconds": poll,
            "server": server,
            "serverSource": source,
            "dayRoot": rule["base_dir"] if rule else None,
            "dayRootSource": rule["source"] if rule else None,
            "dayRootWarning": rule.get("warning") if rule else None,
            "today": today_path(rule),
        })
        errors = []
        if not cfg["enabled"]:
            errors.append("config.json'da enabled=false: runner duraklatildi")
        elif not key:
            errors.append("Anahtar yok: StockTrack > Ayarlar > Corel entegrasyonu'ndaki anahtari "
                          "Corel eklentisine ya da config.json'da api_key'e yazin")
        else:
            api = StockTrack(server, key)
            was_connected = status.get("connected")
            try:
                if not was_connected or time.time() - self.last_ping > PING_EVERY_SECONDS:
                    status["shopName"] = api.ping()
                    self.last_ping = time.time()
                n = poll_once(cfg, state, api, status, errors)
                n += poll_requested(cfg, state, api, status, errors)
                flush_reports(state, api)
                if n:
                    logger.info("%d teklif icin klasorler acildi", n)
                if not was_connected and self.last_error:
                    logger.info("Sunucuya yeniden ulasildi")
                status["connected"] = True
            except ServerError as exc:
                status["connected"] = False
                errors.append(str(exc))
            try:
                api.heartbeat({
                    "host": HOST,
                    "version": VERSION,
                    "startedAt": status.get("startedAt"),
                    "pollSeconds": poll,
                    "dayRoot": rule["base_dir"] if rule else None,
                    "dayRootSource": rule["source"] if rule else None,
                    "error": "; ".join(errors)[:2000] or None,
                })
            except ServerError:
                pass  # baglanti hatasi zaten yukarida yazildi
        error = "; ".join(errors) or None
        # ayni hatayi her turda tekrar yazma
        if error and error != self.last_error:
            logger.warning("%s", error)
        self.last_error = error
        status["error"] = error
        status["pendingReports"] = len(state.unreported)
        status["lastLoopAt"] = now_iso()
        write_status(self.status_path, status)
        return poll


if __name__ == "__main__":
    main()
