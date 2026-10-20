"""Klasor adlari ve klasor acma: Corel eklentisinin (ac2fJob) kurallarinin
aynisi, boylece eklenti runner'in actigi klasorleri tanir, istifler ve
ustune ekler; runner da eklentinin actiklarini.

    <gun klasoru>\\<musteri>\\001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz\\001
                                                                                    \\002
                                                                                    \\u1220x900
    uzun tabaka (boy > 4000 mm):  ...\\003-kompozit-1500x5000--1pcs--4000um-alucobond\\001\\p001
                                                                                        \\p002

Burada dosya sistemi disinda bir seye dokunulmaz; sunucu ve ayarlar
runner.py'de.
"""
import datetime
import math
import os
import re
import unicodedata

# datetime.weekday(): Pazartesi=0 ... Pazar=6 (CDR Auto Renamer ile ayni)
TURKISH_DAYS = ("pazartesi", "sali", "carsamba", "persembe", "cuma", "cumartesi", "pazar")

# Gun klasoru araninca en fazla bu kadar gun geri gidilir (teklif tarihi daha
# eskiyse bile).
MAX_BACK_DAYS = 60

MARKER_DIR = ".stocktrack"


# ---------------------------------------------------------------- adlar

def fold(s):
    """Turkce ve aksanli harfleri ASCII karsiligina katlar."""
    s = (s or "").replace("ı", "i").replace("İ", "I")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c) and ord(c) < 128)


def token(s):
    """Kucuk harf ASCII; harf/rakam disi her dizi tek "-" (eklentinin
    ac2fJBToken'i ve sunucunun nameToken'i ile ayni)."""
    return re.sub(r"[^a-z0-9]+", "-", fold(s).lower()).strip("-")


def day_folder_name(date, date_format="%d-%m-%Y", separator="--"):
    return date.strftime(date_format) + separator + TURKISH_DAYS[date.weekday()]


def size_tok(w, h):
    return "%dx%d" % (int(round(w)), int(round(h)))


def spec(sheet):
    """"2800um-akpolimer-dokme-beyaz": kalinlik, marka, varyant, renk."""
    parts = []
    if sheet.get("thicknessUm"):
        parts.append("%sum" % sheet["thicknessUm"])
    for k in ("brand", "variant", "color"):
        if sheet.get(k):
            parts.append(sheet[k])
    return "-".join(parts)


def group_name(no, head, count, tail, sep="--"):
    s = "%03d-%s%s%dpcs" % (no, head, sep, count)
    return s + sep + tail if tail else s


def split_group(name, sep="--"):
    """"001-pleksi-1220x2440--2pcs--2800um-..." -> (1, "pleksi-1220x2440", 2,
    "2800um-..."); grup klasoru degilse None. Eklentinin ac2fJBSplitGroup'u."""
    if len(name) < 6 or not re.match(r"^\d{3}-", name):
        return None
    rest = name[4:]
    p = rest.find(sep)
    while p > 0:
        q = p + len(sep)
        d = q
        while d < len(rest) and rest[d].isdigit():
            d += 1
        if d > q and rest[d:d + 3].lower() == "pcs":
            after = d + 3
            if after >= len(rest):
                return int(name[:3]), rest[:p], int(rest[q:d]), ""
            if rest[after:after + len(sep)] == sep:
                return int(name[:3]), rest[:p], int(rest[q:d]), rest[after + len(sep):]
        p = rest.find(sep, p + 1)
    return None


def use_name(uw, uh, gw, gh):
    """Kullanilan parca dosyasi: once tabakanin enine denk gelen kenar."""
    if abs(uw - gw) <= 1:
        a, b = uw, uh
    elif abs(uh - gw) <= 1:
        a, b = uh, uw
    elif uw <= gw + 1 and uh <= gh + 1:
        a, b = uw, uh
    else:
        a, b = uh, uw
    return "u%dx%d" % (int(round(a)), int(round(b)))


def same_size(uw, uh, gw, gh):
    return (abs(uw - gw) <= 1 and abs(uh - gh) <= 1) or (abs(uw - gh) <= 1 and abs(uh - gw) <= 1)


def sheets_needed(sheet):
    """Kac tabaka: kullanilan toplam alan / tabaka alani, yukari yuvarlanir.
    Tam tabaka kaleminde adet kadar; 3 x 300x400 parca tek tabakaya sigar."""
    qty = float(sheet.get("quantity") or 0)
    sw, sh = sheet.get("sheetWidthMm"), sheet.get("sheetHeightMm")
    uw, uh = sheet.get("usedWidthMm") or sw, sheet.get("usedHeightMm") or sh
    if qty <= 0:
        qty = 1
    if not (sw and sh and uw and uh):
        return max(1, int(math.ceil(qty - 1e-9)))
    ratio = qty * uw * uh / (sw * sh)
    return max(1, int(math.ceil(ratio - 1e-6)))


def plan_groups(sheets):
    """Tabaka kalemlerinden klasor plani: ayni tur/ebat/kalinlik/marka/
    varyant/renk tek grupta toplanir. [(head, tail, count, sheetW, sheetH,
    [(dosya adi, satir), ...])], kalemlerin geldigi sirayla."""
    plan = []
    index = {}
    for s in sheets:
        sw, sh = s.get("sheetWidthMm"), s.get("sheetHeightMm")
        if not (s.get("kind") and sw and sh):
            continue
        head = "%s-%s" % (s["kind"], size_tok(sw, sh))
        tail = spec(s)
        key = (head.lower(), tail.lower())
        if key not in index:
            index[key] = len(plan)
            plan.append([head, tail, 0, sw, sh, []])
        g = plan[index[key]]
        g[2] += sheets_needed(s)
        uw, uh = s.get("usedWidthMm") or sw, s.get("usedHeightMm") or sh
        if not same_size(uw, uh, sw, sh):
            g[5].append((use_name(uw, uh, sw, sh), s))
    return [tuple(g) for g in plan]


# ---------------------------------------------------------------- yerler

def list_dirs(parent):
    try:
        return sorted(n for n in os.listdir(parent) if os.path.isdir(os.path.join(parent, n)))
    except OSError:
        return []


def find_day_dir(root, date, date_format="%d-%m-%Y", separator="--"):
    """O gunun klasoru: tam adi varsa o, yoksa ayni tarihle baslayan (gun adi
    farkli yazilmis olabilir); hic yoksa None."""
    want = day_folder_name(date, date_format, separator)
    if os.path.isdir(os.path.join(root, want)):
        return os.path.join(root, want)
    stamp = date.strftime(date_format)
    for n in list_dirs(root):
        if n.startswith(stamp):
            return os.path.join(root, n)
    return None


def customer_sub(day_path, customer_folder):
    """Bu gunde musterinin gercek klasoru: bugunku adi ya da ayni okunan eski
    adi ("Ozturk Reklam" -> "ozturk-reklam"). Yoksa None."""
    if not customer_folder:
        return None
    if os.path.isdir(os.path.join(day_path, customer_folder)):
        return customer_folder
    want = token(customer_folder)
    for n in list_dirs(day_path):
        if token(n) == want:
            return n
    return None


def customer_dir(root, rule, customer_folder, created, converted):
    """Isin musteri klasoru. Teklif tarihinden donusum gunune kadar (yeniden
    eskiye) musterinin bir klasoru varsa o: teklif 22'sinde verilip export
    o gunun klasorune yazildiysa, 25'inde donusen is oraya gider. Yoksa
    donusum gununun klasoru altinda yeni klasor (henuz acilmaz).
    (yol, gun klasoru zaten var mi) dondurur."""
    fmt, sep = rule["date_format"], rule["separator"]
    start = max(created, converted - datetime.timedelta(days=MAX_BACK_DAYS))
    d = converted
    while d >= start:
        day = find_day_dir(root, d, fmt, sep)
        if day:
            sub = customer_sub(day, customer_folder)
            if sub:
                return os.path.join(day, sub)
        d -= datetime.timedelta(days=1)
    day = find_day_dir(root, converted, fmt, sep) or os.path.join(root, day_folder_name(converted, fmt, sep))
    return os.path.join(day, customer_folder)


# ---------------------------------------------------------------- acma

def marker_path(cust_dir, quote_id):
    return os.path.join(cust_dir, MARKER_DIR, quote_id + ".done")


def already_done(cust_dir, quote_id):
    return os.path.exists(marker_path(cust_dir, quote_id))


EMPTY_NOTE = "tabaka kalemi yok, yalniz musteri klasoru"


def marker_was_empty(cust_dir, quote_id):
    """Isaret var ama o turda hic tabaka klasoru acilmamis mi (sunucu tam
    tabaka satisini gondermedigi icin bos kalan eski isler)."""
    try:
        with open(marker_path(cust_dir, quote_id), "r", encoding="utf-8") as f:
            return EMPTY_NOTE in f.read()
    except OSError:
        return False


def _hide(path):
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(path, 0x02)  # FILE_ATTRIBUTE_HIDDEN
        except Exception:
            pass


def write_marker(cust_dir, job, report):
    mdir = os.path.join(cust_dir, MARKER_DIR)
    fresh = not os.path.isdir(mdir)
    os.makedirs(mdir, exist_ok=True)
    if fresh:
        _hide(mdir)
    with open(marker_path(cust_dir, job["id"]), "w", encoding="utf-8") as f:
        f.write("Teklif %s, ise donusum %s\n" % (job["quoteNo"], job["convertedAt"]))
        f.write("Runner %s\n\n" % datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))
        f.write("\n".join(report) + "\n")


def make_groups(cust_dir, plan, sep="--", long_mm=4000.0, header=""):
    """Plani diske yazar. Ayni tur/ebat/spec'te grup varsa istifler (adet
    artar, 003 eklenir), yoksa siradaki numarayla yeni grup acar. Uzun
    tabakada her tabaka klasorune p001, p002 ... Kullanilan parca dosyasi
    (u1220x900) grup klasorune, zaten varsa dokunulmaz.
    Yapilanlarin ve sorunlarin listesini dondurur."""
    report, problems = [], []
    os.makedirs(cust_dir, exist_ok=True)

    existing = {}
    max_no = 0
    for n in list_dirs(cust_dir):
        g = split_group(n, sep)
        if not g:
            continue
        no, head, cnt, tail = g
        max_no = max(max_no, no)
        existing.setdefault((head.lower(), tail.lower()), (n, cnt))

    for head, tail, count, sw, sh, uses in plan:
        splits = 0
        if long_mm and sh > long_mm:
            splits = max(2, int(math.ceil(sh / long_mm - 1e-9)))
        key = (head.lower(), tail.lower())
        if key in existing:
            old, old_cnt = existing[key]
            no = int(old[:3])
            name = group_name(no, head, old_cnt + count, tail, sep)
            first = old_cnt + 1
            if name != old:
                try:
                    os.rename(os.path.join(cust_dir, old), os.path.join(cust_dir, name))
                except OSError as exc:
                    problems.append("%s yeniden adlandirilamadi (%s); yeni tabakalar eski adli klasore eklendi" % (old, exc))
                    name = old
            report.append("istif: %s (+%d)" % (name, count))
        else:
            max_no += 1
            no = max_no
            name = group_name(no, head, count, tail, sep)
            first = 1
            report.append("yeni:  %s" % name)
        existing[key] = (name, first + count - 1)

        gdir = os.path.join(cust_dir, name)
        for k in range(first, first + count):
            leaf = os.path.join(gdir, "%03d" % k)
            os.makedirs(leaf, exist_ok=True)
            for q in range(1, splits + 1):
                os.makedirs(os.path.join(leaf, "p%03d" % q), exist_ok=True)

        # ayni dosyaya dusen kalemler (iki 1220x900 parca) tek dosyayi paylasir
        bodies = {}
        for fname, s in uses:
            bodies.setdefault(fname, "")
            bodies[fname] += "%s\nUsed %d x %d mm of the %d x %d mm sheet, qty %s\n" % (
                s.get("label", ""), int(round(s.get("usedWidthMm") or 0)),
                int(round(s.get("usedHeightMm") or 0)), int(round(sw)), int(round(sh)),
                s.get("quantity"))
        for fname, body in bodies.items():
            target = os.path.join(gdir, fname)
            if os.path.exists(target):
                continue
            with open(target, "w", encoding="utf-8") as f:
                f.write(header + body)
            report.append("      %s\\%s" % (name, fname))
    return report, problems
