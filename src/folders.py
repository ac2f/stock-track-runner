"""Klasor adlari ve klasor acma: Corel eklentisinin (ac2fJob) kurallarinin
aynisi, boylece eklenti runner'in actigi klasorleri tanir, istifler ve
ustune ekler; runner da eklentinin actiklarini.

    <gun>\\<musteri>\\001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz--F18-10-2026.merkez.pleksi-beyaz\\001
                                                                                                          \\002
                                                                                                          \\u1220x900
    uzun tabaka (boy > 4000 mm):  ...\\003-kompozit-1500x5000--1pcs--4000um-alucobond--F...\\001\\p001
    malzeme satisi (kesim yok):   ...\\malzeme-F18-10-2026.merkez.pleksi-beyaz\\m1220x2440-2800um-akpolimer-dokme-2adet

Sondaki belirtec: F + projenin gun klasorunun tarihi . malzemenin sahibi
(musterinin malinda musteri klasoru, isletme malinda dukkanin klasor kodu)
. tur-renk. Klasor CNC'ye kopyalansa da kimin, hangi gunun isi oldugu
adindan okunur. Istifte belirtec ayirt edici degildir (adet artar,
belirtec ilk acildigi gibi kalir); sahibi farkli tabaka ayri klasore gider.

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

# Belirtecteki sahip ve tur-renk en fazla bu kadar: Windows yol siniri (260).
OWNER_MAX = 20
KIND_COLOR_MAX = 40
# "F18-10-2026." ya da "malzeme-F18-10-2026." ile baslayan grup: belirtec.
TOKEN_RE = re.compile(r"^(malzeme-)?F\d{2}-\d{2}-\d{4}\.")
SALE_PREFIX = "malzeme-"


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


def clip(s, n):
    return s[:n].rstrip("-") if len(s) > n else s


def folder_token(day, owner, kind, color, sale=False):
    """"F18-10-2026.ozturk-reklam.pleksi-beyaz"; malzeme satisinda basinda
    "malzeme-". `day`: musteri klasorunun bulundugu gun klasorunun tarihi."""
    kc = "-".join(p for p in (token(kind), token(color)) if p)
    t = "F%s.%s.%s" % (day.strftime("%d-%m-%Y"), clip(token(owner) or "isletme", OWNER_MAX),
                       clip(kc or "malzeme", KIND_COLOR_MAX))
    return SALE_PREFIX + t if sale else t


def token_owner(tok):
    """Belirtecteki sahip ("F18-10-2026.merkez.pleksi" -> "merkez")."""
    parts = (tok or "").split(".")
    return parts[1] if len(parts) >= 3 else None


def group_name(no, head, count, tail, sep="--", tok=""):
    s = "%03d-%s%s%dpcs" % (no, head, sep, count)
    s = s + sep + tail if tail else s
    return s + sep + tok if tok else s


def _split(name, sep):
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
                tail = ""
            elif rest[after:after + len(sep)] == sep:
                tail = rest[after + len(sep):]
            else:
                p = rest.find(sep, p + 1)
                continue
            tok = ""
            if TOKEN_RE.match(tail):
                tail, tok = "", tail
            elif sep in tail:
                body, last = tail.rsplit(sep, 1)
                if TOKEN_RE.match(last):
                    tail, tok = body, last
            return int(name[:3]), rest[:p], int(rest[q:d]), tail, tok
        p = rest.find(sep, p + 1)
    return None


def split_group(name, sep="--"):
    """"001-pleksi-1220x2440--2pcs--2800um-...--F18-10-2026.merkez.pleksi" ->
    (1, "pleksi-1220x2440", 2, "2800um-..."); grup klasoru degilse None.
    Sondaki belirtec ayrilir (group_token). Eklentinin ac2fJBSplitGroup'u."""
    g = _split(name, sep)
    return g[:4] if g else None


def group_token(name, sep="--"):
    """Grup klasoru adindaki belirtec; yoksa ""."""
    g = _split(name, sep)
    return g[4] if g else ""


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


def is_sale(sheet):
    """Kesimsiz malzeme satisi mi (sunucu `purpose: "sale"` der)."""
    return sheet.get("purpose") == "sale"


def owner_of(sheet, default="isletme"):
    """Belirtecteki sahip: sunucunun verdigi (musteri klasoru ya da dukkan
    kodu); eski sunucuda dukkanin kodu."""
    return token(sheet.get("owner")) or token(default) or "isletme"


def plan_groups(sheets, default_owner="isletme"):
    """Kesilecek tabaka kalemlerinden klasor plani: ayni tur/ebat/kalinlik/
    marka/varyant/renk ve ayni sahip tek grupta toplanir. Malzeme satisi
    (purpose=sale) burada yoktur. [(head, tail, count, sheetW, sheetH,
    [(dosya adi, satir), ...], sahip, tur, renk)], kalemlerin sirasiyla."""
    plan = []
    index = {}
    for s in sheets:
        if is_sale(s):
            continue
        sw, sh = s.get("sheetWidthMm"), s.get("sheetHeightMm")
        if not (s.get("kind") and sw and sh):
            continue
        head = "%s-%s" % (s["kind"], size_tok(sw, sh))
        tail = spec(s)
        owner = owner_of(s, default_owner)
        key = (head.lower(), tail.lower(), owner)
        if key not in index:
            index[key] = len(plan)
            plan.append([head, tail, 0, sw, sh, [], owner, s.get("kind") or "", s.get("color") or ""])
        g = plan[index[key]]
        g[2] += sheets_needed(s)
        uw, uh = s.get("usedWidthMm") or sw, s.get("usedHeightMm") or sh
        if not same_size(uw, uh, sw, sh):
            g[5].append((use_name(uw, uh, sw, sh), s))
    return [tuple(g) for g in plan]


def qty_text(q):
    v = round(float(q or 0), 2)
    return str(int(v)) if v == int(v) else ("%g" % v)


def material_base(sheet):
    """Satilan olcu dosyasinin adi (adet haric): once tabakanin enine denk
    gelen kenar, sonra kalinlik/marka/varyant ("m1220x2440-2800um-akpolimer-dokme")."""
    sw, sh = sheet.get("sheetWidthMm"), sheet.get("sheetHeightMm")
    uw, uh = sheet.get("usedWidthMm") or sw, sheet.get("usedHeightMm") or sh
    if sw and sh:
        name = "m" + use_name(uw, uh, sw, sh)[1:]
    else:
        name = "m%dx%d" % (int(round(uw or 0)), int(round(uh or 0)))
    rest = spec(dict(sheet, color=""))
    return name + "-" + rest if rest else name


def plan_materials(sheets, default_owner="isletme"):
    """Malzeme satisi kalemleri: tur-renk ve sahip basina bir klasor, icinde
    satilan her olcu bir dosya. [(sahip, tur, renk, [(dosya tabani, adet,
    satir), ...])]"""
    plan, index = [], {}
    for s in sheets:
        if not is_sale(s) or not s.get("kind"):
            continue
        owner = owner_of(s, default_owner)
        key = (s["kind"], s.get("color") or "", owner)
        if key not in index:
            index[key] = len(plan)
            plan.append((owner, s["kind"], s.get("color") or "", []))
        items = plan[index[key]][3]
        base = material_base(s)
        q = float(s.get("quantity") or 1)
        for i, (b, n, rows) in enumerate(items):
            if b == base:
                items[i] = (b, n + q, rows + [s])
                break
        else:
            items.append((base, q, [s]))
    return plan


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


def customer_dir_and_day(root, rule, customer_folder, created, converted):
    """Isin musteri klasoru ve bulundugu gun klasorunun tarihi. Teklif
    tarihinden donusum gunune kadar (yeniden eskiye) musterinin bir klasoru
    varsa o: teklif 22'sinde verilip export o gunun klasorune yazildiysa,
    25'inde donusen is oraya gider (belirtec F22-...). Yoksa donusum
    gununun klasoru altinda yeni klasor (henuz acilmaz)."""
    fmt, sep = rule["date_format"], rule["separator"]
    start = max(created, converted - datetime.timedelta(days=MAX_BACK_DAYS))
    d = converted
    while d >= start:
        day = find_day_dir(root, d, fmt, sep)
        if day:
            sub = customer_sub(day, customer_folder)
            if sub:
                return os.path.join(day, sub), d
        d -= datetime.timedelta(days=1)
    day = find_day_dir(root, converted, fmt, sep) or os.path.join(root, day_folder_name(converted, fmt, sep))
    return os.path.join(day, customer_folder), converted


def customer_dir(root, rule, customer_folder, created, converted):
    """Isin musteri klasoru (bkz. customer_dir_and_day)."""
    return customer_dir_and_day(root, rule, customer_folder, created, converted)[0]


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


def make_groups(cust_dir, plan, sep="--", long_mm=4000.0, header="", day=None):
    """Plani diske yazar. Ayni tur/ebat/spec ve ayni sahipte grup varsa
    istifler (adet artar, 003 eklenir), yoksa siradaki numarayla yeni grup
    acar; yeni grubun sonuna belirtec (F<gun>.<sahip>.<tur>-<renk>), belirteci
    olmayan eski gruba da istiflerken eklenir. Uzun tabakada her tabaka
    klasorune p001, p002 ... Kullanilan parca dosyasi (u1220x900) grup
    klasorune, zaten varsa dokunulmaz.
    Yapilanlarin ve sorunlarin listesini dondurur."""
    report, problems = [], []
    day = day or datetime.date.today()
    os.makedirs(cust_dir, exist_ok=True)

    existing = {}
    max_no = 0
    for n in list_dirs(cust_dir):
        g = _split(n, sep)
        if not g:
            continue
        no, head, cnt, tail, tok = g
        max_no = max(max_no, no)
        existing.setdefault((head.lower(), tail.lower()), []).append([n, cnt, token_owner(tok), tok])

    for entry in plan:
        head, tail, count, sw, sh, uses = entry[:6]
        owner, kind, color = (entry[6:9] if len(entry) >= 9 else ("isletme", head.split("-")[0], ""))
        splits = 0
        if long_mm and sh > long_mm:
            splits = max(2, int(math.ceil(sh / long_mm - 1e-9)))
        key = (head.lower(), tail.lower())
        # ayni sahibin grubu; belirteci olmayan (eski/eklentinin) grup herkese uyar
        match = None
        for g in existing.get(key, []):
            if g[2] == owner:
                match = g
                break
        if match is None:
            for g in existing.get(key, []):
                if g[2] is None:
                    match = g
                    break
        if match is not None:
            old, old_cnt, _o, old_tok = match
            no = int(old[:3])
            tok = old_tok or folder_token(day, owner, kind, color)
            name = group_name(no, head, old_cnt + count, tail, sep, tok)
            first = old_cnt + 1
            if name != old:
                try:
                    os.rename(os.path.join(cust_dir, old), os.path.join(cust_dir, name))
                except OSError as exc:
                    problems.append("%s yeniden adlandirilamadi (%s); yeni tabakalar eski adli klasore eklendi" % (old, exc))
                    name = old
            report.append("istif: %s (+%d)" % (name, count))
            match[:] = [name, first + count - 1, token_owner(tok), tok]
        else:
            max_no += 1
            no = max_no
            tok = folder_token(day, owner, kind, color)
            name = group_name(no, head, count, tail, sep, tok)
            first = 1
            report.append("yeni:  %s" % name)
            existing.setdefault(key, []).append([name, count, owner, tok])

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


def material_folder(cust_dir, day, owner, kind, color):
    """Malzeme satisi klasoru: ayni sahip ve tur-renkte daha once acilmis
    (baska gunun tarihiyle de olsa) varsa o, yoksa yeni ad."""
    tail = ".%s.%s" % (clip(token(owner) or "isletme", OWNER_MAX),
                       clip("-".join(p for p in (token(kind), token(color)) if p) or "malzeme", KIND_COLOR_MAX))
    for n in list_dirs(cust_dir):
        if n.startswith(SALE_PREFIX) and TOKEN_RE.match(n) and n.endswith(tail):
            return n
    return folder_token(day, owner, kind, color, sale=True)


def make_materials(cust_dir, plan, header="", day=None, quote_no=""):
    """Malzeme satislarini diske yazar: tur-renk ve sahip basina bir
    malzeme-F... klasoru (tabaka klasoru yok, kesim yok), satilan her olcu
    bir m dosyasi: m1220x2440-2800um-akpolimer-dokme-2adet. Ayni olcu tekrar
    satilirsa dosyanin adedi artar ve satir eklenir; ayni teklif ikinci kez
    yazilmaz. Yapilanlarin ve sorunlarin listesini dondurur."""
    report, problems = [], []
    day = day or datetime.date.today()
    for owner, kind, color, items in plan:
        folder = material_folder(cust_dir, day, owner, kind, color)
        mdir = os.path.join(cust_dir, folder)
        os.makedirs(mdir, exist_ok=True)
        files = sorted(n for n in os.listdir(mdir) if os.path.isfile(os.path.join(mdir, n)))
        for base, qty, rows in items:
            pat = re.compile("^" + re.escape(base) + r"-(\d+(?:\.\d+)?)adet$")
            old = next((n for n in files if pat.match(n)), None)
            body = ""
            for s in rows:
                sw, sh = s.get("sheetWidthMm"), s.get("sheetHeightMm")
                uw, uh = s.get("usedWidthMm") or sw, s.get("usedHeightMm") or sh
                size = "%d x %d mm" % (int(round(uw or 0)), int(round(uh or 0)))
                whole = sw and sh and same_size(uw, uh, sw, sh)
                body += "%s\nMATERIAL SALE, no cutting (malzeme satisi): %s x %s%s\n" % (
                    s.get("label", ""), qty_text(s.get("quantity") or 1), size,
                    " whole sheet" if whole or not (sw and sh) else
                    " of the %d x %d mm sheet" % (int(round(sw)), int(round(sh))))
            if old:
                path = os.path.join(mdir, old)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                except OSError:
                    text = ""
                if quote_no and ("Quote %s " % quote_no) in text:
                    continue
                total = float(pat.match(old).group(1)) + qty
                name = "%s-%sadet" % (base, qty_text(total))
                try:
                    os.rename(path, os.path.join(mdir, name))
                except OSError as exc:
                    problems.append("%s yeniden adlandirilamadi (%s)" % (old, exc))
                    name = old
                with open(os.path.join(mdir, name), "a", encoding="utf-8") as f:
                    f.write("\n" + header + body)
                files = [name if n == old else n for n in files]
                report.append("malzeme: %s\\%s (+%s)" % (folder, name, qty_text(qty)))
            else:
                name = "%s-%sadet" % (base, qty_text(qty))
                with open(os.path.join(mdir, name), "w", encoding="utf-8") as f:
                    f.write(header + body)
                files.append(name)
                report.append("malzeme: %s\\%s" % (folder, name))
    return report, problems
