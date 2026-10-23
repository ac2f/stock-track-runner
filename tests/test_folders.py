import datetime
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import folders as F  # noqa: E402
import runner as R  # noqa: E402
from config import Config  # noqa: E402
from stocktrack import StockTrack  # noqa: E402

D = datetime.date
RULE = {"date_format": "%d-%m-%Y", "separator": "--"}
TOK = "--F18-10-2026.isletme.pleksi-beyaz"


def sheet(**kw):
    s = {"itemId": "i1", "label": "Pleksi 2.8mm Akpolimer Dokme Beyaz 1220x2440", "kind": "pleksi",
         "thicknessUm": "2800", "brand": "akpolimer", "variant": "dokme", "color": "beyaz",
         "sheetWidthMm": 1220, "sheetHeightMm": 2440, "usedWidthMm": 1220, "usedHeightMm": 2440,
         "quantity": 1}
    s.update(kw)
    return s


def tree(root):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != F.MARKER_DIR]
        rel = os.path.relpath(dp, root)
        for n in sorted(dn) + sorted(fn):
            out.append(os.path.normpath(os.path.join(rel, n)).replace(os.sep, "/"))
    return sorted(out)


class Names(unittest.TestCase):
    def test_names_match_the_corel_add_on(self):
        self.assertEqual(F.day_folder_name(D(2026, 10, 18)), "18-10-2026--pazar")
        self.assertEqual(F.token("Öztürk Reklam Ltd. Şti."), "ozturk-reklam-ltd-sti")
        self.assertEqual(F.token("  İĞNE  Işık "), "igne-isik")
        self.assertEqual(F.spec(sheet()), "2800um-akpolimer-dokme-beyaz")
        self.assertEqual(F.spec(sheet(thicknessUm="", brand="", variant="")), "beyaz")
        self.assertEqual(F.group_name(1, "pleksi-1220x2440", 2, "2800um-akpolimer-dokme-beyaz"),
                         "001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz")
        self.assertEqual(F.split_group("001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz"),
                         (1, "pleksi-1220x2440", 2, "2800um-akpolimer-dokme-beyaz"))
        self.assertEqual(F.split_group("012-dekota-1560x3050--1pcs"), (12, "dekota-1560x3050", 1, ""))
        self.assertIsNone(F.split_group("exp01--pleksi.dxf"))
        self.assertIsNone(F.split_group("u1220x900"))
        self.assertIsNone(F.split_group("malzeme-F18-10-2026.merkez.pleksi-beyaz"))

    def test_token_names_day_owner_and_material(self):
        tok = F.folder_token(D(2026, 10, 18), "Öztürk Reklam", "pleksi", "beyaz")
        self.assertEqual(tok, "F18-10-2026.ozturk-reklam.pleksi-beyaz")
        self.assertEqual(F.folder_token(D(2026, 10, 18), "merkez", "pleksi", "", sale=True),
                         "malzeme-F18-10-2026.merkez.pleksi")
        # cok uzun sahip ve tur-renk kisaltilir (Windows yol siniri)
        long_tok = F.folder_token(D(2026, 10, 18), "a" * 50, "aluminyum-kompozit", "gumus-metalik-fircali-ozel")
        self.assertEqual(long_tok.split(".")[1], "a" * 20)
        self.assertLessEqual(len(long_tok.split(".")[2]), 40)
        name = F.group_name(1, "pleksi-1220x2440", 2, "2800um-akpolimer-dokme-beyaz", "--", tok)
        self.assertEqual(name, "001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz--F18-10-2026.ozturk-reklam.pleksi-beyaz")
        # belirtec istif anahtarina girmez, ayri okunur
        self.assertEqual(F.split_group(name), (1, "pleksi-1220x2440", 2, "2800um-akpolimer-dokme-beyaz"))
        self.assertEqual(F.group_token(name), tok)
        self.assertEqual(F.token_owner(F.group_token(name)), "ozturk-reklam")
        bare = F.group_name(12, "dekota-1560x3050", 1, "", "--", "F01-02-2026.merkez.dekota")
        self.assertEqual(F.split_group(bare), (12, "dekota-1560x3050", 1, ""))
        self.assertEqual(F.group_token(bare), "F01-02-2026.merkez.dekota")
        self.assertEqual(F.group_token("001-pleksi-1220x2440--2pcs--2800um"), "")
        # baska ayracla da
        self.assertEqual(F.split_group("001-pleksi-1220x2440__2pcs__2800um__F18-10-2026.m.pleksi", "__"),
                         (1, "pleksi-1220x2440", 2, "2800um"))

    def test_use_name_puts_the_sheet_width_first(self):
        self.assertEqual(F.use_name(1220, 900, 1220, 2440), "u1220x900")
        self.assertEqual(F.use_name(900, 1220, 1220, 2440), "u1220x900")
        self.assertEqual(F.use_name(500, 300, 1220, 2440), "u500x300")

    def test_sheet_count_from_area(self):
        self.assertEqual(F.sheets_needed(sheet(quantity=2)), 2)
        self.assertEqual(F.sheets_needed(sheet(usedHeightMm=900, quantity=1)), 1)
        self.assertEqual(F.sheets_needed(sheet(usedWidthMm=300, usedHeightMm=400, quantity=3)), 1)
        self.assertEqual(F.sheets_needed(sheet(usedHeightMm=1500, quantity=2)), 2)
        self.assertEqual(F.sheets_needed(sheet(sheetWidthMm=None, quantity=2.5)), 3)


class Groups(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.cust = os.path.join(self.root, "18-10-2026--pazar", "ozturk-reklam")

    def test_new_groups_stack_and_long_sheets(self):
        plan = F.plan_groups([
            sheet(quantity=2),
            sheet(itemId="i2", quantity=1),                       # ayni plaka: ayni gruba
            sheet(itemId="i3", color="siyah", usedHeightMm=900),  # farkli renk: yeni grup
            sheet(itemId="i4", kind="aluminyum-kompozit", thicknessUm="4000", brand="alucobond",
                  variant="", color="gumus", sheetWidthMm=1500, sheetHeightMm=5000,
                  usedWidthMm=1500, usedHeightMm=5000),
        ])
        report, problems = F.make_groups(self.cust, plan, header="Quote TKF-2026-0007  2026-10-17\n",
                                         day=D(2026, 10, 18))
        self.assertEqual(problems, [])
        t = tree(self.cust)
        white = "001-pleksi-1220x2440--3pcs--2800um-akpolimer-dokme-beyaz--F18-10-2026.isletme.pleksi-beyaz"
        black = "002-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-siyah--F18-10-2026.isletme.pleksi-siyah"
        acp = "003-aluminyum-kompozit-1500x5000--1pcs--4000um-alucobond-gumus--F18-10-2026.isletme.aluminyum-kompozit-gumus"
        self.assertIn(white + "/003", t)
        self.assertNotIn(white + "/004", t)
        self.assertIn(black + "/001", t)
        self.assertIn(black + "/u1220x900", t)
        self.assertIn(acp + "/001/p002", t)
        self.assertNotIn(acp + "/001/p003", t)
        with open(os.path.join(self.cust, black, "u1220x900"), encoding="utf-8") as f:
            body = f.read()
        self.assertIn("Quote TKF-2026-0007", body)
        self.assertIn("Used 1220 x 900 mm of the 1220 x 2440 mm sheet", body)

    def test_stacks_onto_folders_the_add_on_made(self):
        os.makedirs(os.path.join(self.cust, "001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz", "002"))
        os.makedirs(os.path.join(self.cust, "004-dekota-1560x3050--1pcs--5000um", "001"))
        open(os.path.join(self.cust, "exp01--pleksi.dxf"), "w").close()
        F.make_groups(self.cust, F.plan_groups([sheet(quantity=1), sheet(color="mavi")]), day=D(2026, 10, 18))
        t = tree(self.cust)
        # belirteci olmayan (eklentinin eski) gruba istiflenir ve belirtec eklenir
        self.assertIn("001-pleksi-1220x2440--3pcs--2800um-akpolimer-dokme-beyaz" + TOK + "/003", t)
        self.assertIn("005-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-mavi--F18-10-2026.isletme.pleksi-mavi/001", t)
        self.assertIn("exp01--pleksi.dxf", t)

    def test_token_stays_as_first_made_and_owners_do_not_mix(self):
        first = "001-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-beyaz--F15-10-2026.merkez.pleksi-beyaz"
        os.makedirs(os.path.join(self.cust, first, "001"))
        plan = F.plan_groups([
            sheet(owner="merkez"),                       # ayni sahip: istif, belirtec 15'inde kalir
            sheet(itemId="i2", owner="ozturk-reklam"),   # musterinin kendi malzemesi: ayri grup
        ])
        F.make_groups(self.cust, plan, day=D(2026, 10, 18))
        t = tree(self.cust)
        self.assertIn("001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz--F15-10-2026.merkez.pleksi-beyaz/002", t)
        self.assertIn("002-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-beyaz--F18-10-2026.ozturk-reklam.pleksi-beyaz/001", t)

    def test_material_sale_gets_a_material_folder_and_m_file_not_toolpaths(self):
        sale = [sheet(purpose="sale", owner="merkez", quantity=2),
                sheet(itemId="i2", purpose="sale", owner="merkez", usedHeightMm=900, quantity=1)]
        self.assertEqual(F.plan_groups(sale), [])
        header = "Quote TKF-2026-0009  2026-10-18\n"
        report, problems = F.make_materials(self.cust, F.plan_materials(sale), header, D(2026, 10, 18), "TKF-2026-0009")
        self.assertEqual(problems, [])
        t = tree(self.cust)
        folder = "malzeme-F18-10-2026.merkez.pleksi-beyaz"
        self.assertIn(folder + "/m1220x2440-2800um-akpolimer-dokme-2adet", t)
        self.assertIn(folder + "/m1220x900-2800um-akpolimer-dokme-1adet", t)
        self.assertFalse(any("pcs" in x for x in t))
        with open(os.path.join(self.cust, folder, "m1220x900-2800um-akpolimer-dokme-1adet"), encoding="utf-8") as f:
            body = f.read()
        self.assertIn("MATERIAL SALE", body)
        self.assertIn("of the 1220 x 2440 mm sheet", body)
        # ayni teklif ikinci kez yazilmaz; baska gun baska teklifle ayni olcu adedi artirir
        F.make_materials(self.cust, F.plan_materials(sale[:1]), header, D(2026, 10, 18), "TKF-2026-0009")
        self.assertIn(folder + "/m1220x2440-2800um-akpolimer-dokme-2adet", tree(self.cust))
        F.make_materials(self.cust, F.plan_materials(sale[:1]), "Quote TKF-2026-0011  2026-10-20\n",
                         D(2026, 10, 20), "TKF-2026-0011")
        t = tree(self.cust)
        self.assertIn(folder + "/m1220x2440-2800um-akpolimer-dokme-4adet", t)
        self.assertNotIn("malzeme-F20-10-2026.merkez.pleksi-beyaz", t)

    def test_customer_folder_on_an_earlier_day_and_legacy_names(self):
        old = os.path.join(self.root, "15-10-2026--persembe", "Ozturk Reklam")
        os.makedirs(old)
        # teklif 15'inde, donusum 18'inde: 15'indeki (eski adli) klasor
        self.assertEqual(F.customer_dir(self.root, RULE, "ozturk-reklam", D(2026, 10, 15), D(2026, 10, 18)), old)
        # teklif 16'sinda verildiyse 15'indeki baska istir: bugunun altinda yeni
        self.assertEqual(F.customer_dir(self.root, RULE, "ozturk-reklam", D(2026, 10, 16), D(2026, 10, 18)),
                         os.path.join(self.root, "18-10-2026--pazar", "ozturk-reklam"))
        # gun klasoru farkli yazilmissa (gun adi) tarihle bulunur
        os.makedirs(os.path.join(self.root, "17-10-2026--cmt", "ozturk-reklam"))
        self.assertEqual(F.customer_dir(self.root, RULE, "ozturk-reklam", D(2026, 10, 16), D(2026, 10, 18)),
                         os.path.join(self.root, "17-10-2026--cmt", "ozturk-reklam"))

    def test_rename_failure_keeps_going(self):
        os.makedirs(os.path.join(self.cust, "001-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-beyaz", "001"))
        real = os.rename

        def boom(a, b):
            raise OSError("kullanimda")
        os.rename = boom
        try:
            report, problems = F.make_groups(self.cust, F.plan_groups([sheet()]))
        finally:
            os.rename = real
        self.assertTrue(problems)
        self.assertIn("001-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-beyaz/002", tree(self.cust))

    def test_customer_dir_and_day_gives_the_project_day(self):
        old = os.path.join(self.root, "15-10-2026--persembe", "ozturk-reklam")
        os.makedirs(old)
        self.assertEqual(F.customer_dir_and_day(self.root, RULE, "ozturk-reklam", D(2026, 10, 15), D(2026, 10, 18)),
                         (old, D(2026, 10, 15)))


class FakeServer(BaseHTTPRequestHandler):
    jobs = []
    requested = []
    calls = []
    posts = []
    settings = None

    def _auth(self):
        if self.headers.get("X-Api-Key") != "k":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"message":"Gecersiz anahtar"}')
            return False
        return True

    def do_GET(self):
        FakeServer.calls.append((self.path, self.headers.get("X-Api-Key")))
        if not self._auth():
            return
        if self.path.startswith("/api/v1/corel/ping"):
            body = b"#ac2f-corel 1\nok\tAcme Reklam\tacme\n"
        elif self.path.startswith("/api/v1/corel/folder-settings"):
            if FakeServer.settings is None:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"message":"Not Found"}')
                return
            body = json.dumps({"success": True, "data": FakeServer.settings}).encode()
        elif self.path.startswith("/api/v1/corel/jobs/requested"):
            body = json.dumps({"success": True, "data": FakeServer.requested}).encode()
        else:
            body = json.dumps({"success": True, "data": FakeServer.jobs}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._auth():
            return
        length = int(self.headers.get("Content-Length") or 0)
        FakeServer.posts.append((self.path, json.loads(self.rfile.read(length) or b"{}")))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"success":true,"data":{"ok":true}}')

    def log_message(self, *a):
        pass


WHITE = "001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz"


class Poll(unittest.TestCase):
    def setUp(self):
        FakeServer.settings = None
        FakeServer.calls = []
        FakeServer.posts = []
        FakeServer.requested = []
        self.srv = HTTPServer(("127.0.0.1", 0), FakeServer)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.dir = tempfile.mkdtemp()
        self.root = os.path.join(self.dir, "Gunluk")
        cfgp = os.path.join(self.dir, "config.json")
        with open(cfgp, "w") as f:
            json.dump({"server": "http://127.0.0.1:%d/api/v1" % self.srv.server_port, "api_key": "k",
                       "day_folders": {"base_dir": self.root}}, f)
        self.cfg = Config(cfgp)
        self.api = StockTrack(self.cfg["server"], "k")
        now = datetime.datetime.now(datetime.timezone.utc)
        FakeServer.jobs = [{
            "id": "q1", "quoteNo": "TKF-2026-0007", "createdAt": now.isoformat(),
            "convertedAt": now.isoformat(), "customerId": "c1", "customerFolder": "ozturk-reklam",
            "customerLabel": "Ozturk Reklam", "sheets": [sheet(quantity=2)],
        }]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_poll_makes_folders_once(self):
        state = R.State(os.path.join(self.dir, "state.json"))
        self.assertEqual(R.poll_once(self.cfg, state, self.api), 1)
        day = F.day_folder_name(datetime.date.today())
        t = tree(self.root)
        stamp = datetime.date.today().strftime("%d-%m-%Y")
        self.assertIn(day + "/ozturk-reklam/" + WHITE + "--F%s.isletme.pleksi-beyaz/002" % stamp, t)
        # ikinci tur: ayni teklif yeniden islenmez, istif 4pcs olmaz
        self.assertEqual(R.poll_once(self.cfg, state, self.api), 0)
        # durum dosyasi silinse bile klasordeki isaret tekrari onler
        state2 = R.State(os.path.join(self.dir, "yok.json"))
        R.poll_once(self.cfg, state2, self.api)
        self.assertNotIn(day + "/ozturk-reklam/001-pleksi-1220x2440--4pcs--2800um-akpolimer-dokme-beyaz", tree(self.root))
        self.assertTrue(FakeServer.calls[0][0].startswith("/api/v1/corel/jobs?since="))

    def test_bad_key_is_a_server_error(self):
        with self.assertRaises(R.ServerError):
            StockTrack(self.cfg["server"], "yanlis").jobs()
        self.assertEqual(StockTrack(self.cfg["server"], "k").ping(), "Acme Reklam")

    def test_day_rule_from_cdr_auto_renamer(self):
        rc = os.path.join(self.dir, "renamer.json")
        with open(rc, "w") as f:
            json.dump({"daily_folders": {"enabled": True, "base_dir": "D:\\Isler", "date_format": "%d.%m.%Y",
                                         "separator": "_"}}, f)
        cfgp = os.path.join(self.dir, "c2.json")
        with open(cfgp, "w") as f:
            json.dump({"day_folders": {"base_dir": "", "renamer_config": rc}}, f)
        rule = Config(cfgp).day_rule()
        self.assertEqual((rule["base_dir"], rule["date_format"], rule["separator"]), ("D:\\Isler", "%d.%m.%Y", "_"))


    def test_loop_reports_folders_heartbeat_and_status(self):
        state = R.State(os.path.join(self.dir, "state.json"))
        status_path = os.path.join(self.dir, "status.json")
        status = {}
        loop = R.Loop(self.cfg, state, status, status_path)
        self.assertEqual(loop.tick(), 30)
        paths = [p for p, _ in FakeServer.posts]
        self.assertIn("/api/v1/corel/jobs/q1/folders", paths)
        self.assertIn("/api/v1/corel/runner/heartbeat", paths)
        report = dict(FakeServer.posts)["/api/v1/corel/jobs/q1/folders"]
        self.assertTrue(report["folder"].endswith("ozturk-reklam"))
        self.assertEqual(report["host"], R.HOST)
        beat = dict(FakeServer.posts)["/api/v1/corel/runner/heartbeat"]
        self.assertIsNone(beat["error"])
        self.assertEqual(beat["dayRoot"], self.root)
        saved = R.read_status(status_path)
        self.assertTrue(saved["connected"])
        self.assertEqual(saved["shopName"], "Acme Reklam")
        self.assertEqual(saved["recent"][0]["quoteNo"], "TKF-2026-0007")
        self.assertEqual(state.unreported, {})

    def test_requested_job_is_reported_again_without_restacking(self):
        state = R.State(os.path.join(self.dir, "state.json"))
        R.poll_once(self.cfg, state, self.api)
        R.flush_reports(state, self.api)
        FakeServer.posts = []
        FakeServer.requested = FakeServer.jobs
        self.assertEqual(R.poll_requested(self.cfg, state, self.api), 1)
        R.flush_reports(state, self.api)
        report = dict(FakeServer.posts)["/api/v1/corel/jobs/q1/folders"]
        self.assertIn("zaten acilmis", report["report"][0])
        day = F.day_folder_name(datetime.date.today())
        self.assertNotIn(day + "/ozturk-reklam/001-pleksi-1220x2440--4pcs--2800um-akpolimer-dokme-beyaz",
                         tree(self.root))

    def test_requested_job_reopens_when_first_run_had_no_sheets(self):
        # Eski sunucu tam tabaka satisini tabakasiz gonderdi: isaret var ama bos.
        state = R.State(os.path.join(self.dir, "state.json"))
        sheets = FakeServer.jobs[0]["sheets"]
        FakeServer.jobs[0]["sheets"] = []
        R.poll_once(self.cfg, state, self.api)
        R.flush_reports(state, self.api)
        day = F.day_folder_name(datetime.date.today())
        self.assertFalse(any("001-" in p for p in tree(self.root)))
        # Duzeltilmis sunucu tabakayla gonderir, klasor yeniden istenir.
        FakeServer.jobs[0]["sheets"] = sheets
        FakeServer.requested = FakeServer.jobs
        R.poll_requested(self.cfg, state, self.api)
        R.flush_reports(state, self.api)
        self.assertTrue(any(x.startswith(day + "/ozturk-reklam/" + WHITE + "--F") and x.endswith("/002")
                            for x in tree(self.root)))
        # bir daha istense de ikinci kez istiflenmez
        R.poll_requested(self.cfg, state, self.api)
        R.flush_reports(state, self.api)
        self.assertNotIn(day + "/ozturk-reklam/001-pleksi-1220x2440--4pcs--2800um-akpolimer-dokme-beyaz",
                         tree(self.root))

    def test_shop_settings_from_stocktrack_code_material_and_day_root(self):
        own_root = os.path.join(self.dir, "MerkezGunluk")
        FakeServer.settings = {"enabled": True, "code": "merkez", "materialSaleFolders": True,
                               "dayRoot": own_root, "shopName": "Merkez"}
        cfgp = os.path.join(self.dir, "c4.json")
        with open(cfgp, "w") as f:
            json.dump({"server": self.cfg["server"], "api_key": "k",
                       "day_folders": {"base_dir": "", "renamer_config": os.path.join(self.dir, "yok.json")}}, f)
        cfg = Config(cfgp, addon_reader=lambda: {})
        FakeServer.jobs[0]["shopCode"] = "merkez"
        FakeServer.jobs[0]["sheets"] = [sheet(quantity=1, owner="merkez"),
                                        sheet(itemId="i2", color="siyah", purpose="sale", owner="merkez")]
        status = {}
        R.Loop(cfg, R.State(os.path.join(self.dir, "s4.json")), status, os.path.join(self.dir, "st4.json")).tick()
        self.assertIsNone(status["error"])
        self.assertEqual((status["dayRoot"], status["dayRootSource"]), (own_root, "StockTrack (dukkan ayari)"))
        day = F.day_folder_name(datetime.date.today())
        stamp = datetime.date.today().strftime("%d-%m-%Y")
        t = tree(own_root)
        self.assertIn(day + "/ozturk-reklam/001-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-beyaz"
                      "--F%s.merkez.pleksi-beyaz/001" % stamp, t)
        self.assertIn(day + "/ozturk-reklam/malzeme-F%s.merkez.pleksi-siyah/m1220x2440-2800um-akpolimer-dokme-1adet"
                      % stamp, t)
        report = dict(FakeServer.posts)["/api/v1/corel/jobs/q1/folders"]
        self.assertTrue(any(r.startswith("malzeme:") for r in report["report"]))

    def test_shop_switched_off_in_stocktrack_opens_nothing(self):
        FakeServer.settings = {"enabled": False, "code": "merkez", "materialSaleFolders": True, "dayRoot": ""}
        FakeServer.jobs = []  # sunucu kapali dukkana is gondermez
        status = {}
        R.Loop(self.cfg, R.State(os.path.join(self.dir, "s5.json")), status, os.path.join(self.dir, "st5.json")).tick()
        self.assertIsNone(status["error"])
        self.assertIn("kapali", status["note"])

    def test_material_sale_folders_off(self):
        FakeServer.jobs[0]["materialSaleFolders"] = False
        FakeServer.jobs[0]["sheets"] = [sheet(purpose="sale", owner="acme")]
        state = R.State(os.path.join(self.dir, "s6.json"))
        R.poll_once(self.cfg, state, self.api)
        self.assertFalse(any("malzeme-" in x or "pcs" in x for x in tree(self.root)))

    def test_missing_day_folder_is_reported_as_error(self):
        cfgp = os.path.join(self.dir, "c3.json")
        with open(cfgp, "w") as f:
            json.dump({"server": self.cfg["server"], "api_key": "k",
                       "day_folders": {"base_dir": "", "renamer_config": os.path.join(self.dir, "yok.json")}}, f)
        cfg = Config(cfgp)
        status = {}
        R.Loop(cfg, R.State(os.path.join(self.dir, "s3.json")), status, os.path.join(self.dir, "st3.json")).tick()
        self.assertIn("Gun klasoru bilinmiyor", status["error"])
        beat = dict(FakeServer.posts)["/api/v1/corel/runner/heartbeat"]
        self.assertIn("Gun klasoru bilinmiyor", beat["error"])

    def test_server_address_without_scheme_is_an_error_not_a_crash(self):
        with self.assertRaises(R.ServerError):
            StockTrack("192.168.1.50/api/v1", "k").ping()
        with self.assertRaises(R.ServerError):
            StockTrack("", "k").ping()


class MultiShop(unittest.TestCase):
    """Bir bilgisayar iki dukkana klasor aciyor: her dukkan kendi anahtari,
    durum dosyasi, gun klasoru ve nabziyla, ayri ayri."""

    class Two(BaseHTTPRequestHandler):
        jobs = {}
        posts = []

        def do_GET(self):
            key = self.headers.get("X-Api-Key")
            if key not in self.jobs:
                self.send_response(401)
                self.end_headers()
                return
            if self.path.startswith("/api/v1/corel/ping"):
                body = ("#ac2f-corel 1\nok\t%s\t%s\n" % ({"ka": "Merkez", "kb": "Sube"}[key],
                                                           {"ka": "merkez", "kb": "sube"}[key])).encode()
            elif self.path.startswith("/api/v1/corel/folder-settings"):
                body = json.dumps({"enabled": True, "code": {"ka": "merkez", "kb": "sube"}[key],
                                   "materialSaleFolders": True, "dayRoot": ""}).encode()
            elif self.path.startswith("/api/v1/corel/jobs/requested"):
                body = b"[]"
            else:
                body = json.dumps(self.jobs[key]).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            MultiShop.Two.posts.append((self.headers.get("X-Api-Key"), self.path,
                                        json.loads(self.rfile.read(length) or b"{}")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    def setUp(self):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        job = lambda qid, code: {"id": qid, "quoteNo": qid, "createdAt": now, "convertedAt": now,
                                 "customerId": "c", "customerFolder": "ali", "customerLabel": "Ali",
                                 "shopCode": code, "sheets": [sheet(owner=code)]}
        MultiShop.Two.jobs = {"ka": [job("TA-1", "merkez")], "kb": [job("TB-1", "sube")]}
        MultiShop.Two.posts = []
        self.srv = HTTPServer(("127.0.0.1", 0), MultiShop.Two)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.dir = tempfile.mkdtemp()
        self.server = "http://127.0.0.1:%d/api/v1" % self.srv.server_port

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_each_shop_has_its_own_folders_state_and_heartbeat(self):
        ra, rb = os.path.join(self.dir, "A"), os.path.join(self.dir, "B")
        cfgp = os.path.join(self.dir, "c.json")
        with open(cfgp, "w") as f:
            json.dump({"server": self.server, "shops": [
                {"name": "Merkez", "api_key": "ka", "day_folders": {"base_dir": ra}},
                {"name": "Sube", "api_key": "kb", "day_folders": {"base_dir": rb}},
            ]}, f)
        cfg = Config(cfgp, addon_reader=lambda: {})
        old_base = R.BASE_DIR
        R.BASE_DIR = self.dir
        try:
            status = {}
            loop = R.Loop(cfg, R.State(os.path.join(self.dir, "state.json")), status, os.path.join(self.dir, "st.json"))
            loop.tick()
        finally:
            R.BASE_DIR = old_base
        self.assertIsNone(status["error"])
        self.assertEqual([e["shopName"] for e in status["shops"]], ["Merkez", "Sube"])
        ta = tree(ra)
        tb = tree(rb)
        self.assertTrue(any(".merkez.pleksi-beyaz" in x for x in ta))
        self.assertFalse(any(".sube." in x for x in ta))
        self.assertTrue(any(".sube.pleksi-beyaz" in x for x in tb))
        beats = [k for k, p, _ in MultiShop.Two.posts if p.endswith("/runner/heartbeat")]
        self.assertEqual(sorted(beats), ["ka", "kb"])
        reports = [(k, p) for k, p, _ in MultiShop.Two.posts if "/folders" in p]
        self.assertEqual(sorted(reports), [("ka", "/api/v1/corel/jobs/TA-1/folders"),
                                           ("kb", "/api/v1/corel/jobs/TB-1/folders")])
        # ikinci dukkanin durum dosyasi ayri
        self.assertTrue(any(n.startswith("state-") for n in os.listdir(self.dir)))

    def test_same_day_root_for_two_shops_is_a_warning(self):
        root = os.path.join(self.dir, "Ortak")
        cfgp = os.path.join(self.dir, "c.json")
        with open(cfgp, "w") as f:
            json.dump({"server": self.server, "shops": [
                {"name": "Merkez", "api_key": "ka", "day_folders": {"base_dir": root}},
                {"name": "Sube", "api_key": "kb", "day_folders": {"base_dir": root}},
            ]}, f)
        cfg = Config(cfgp, addon_reader=lambda: {})
        old_base = R.BASE_DIR
        R.BASE_DIR = self.dir
        try:
            status = {}
            R.Loop(cfg, R.State(os.path.join(self.dir, "state.json")), status, os.path.join(self.dir, "st.json")).tick()
        finally:
            R.BASE_DIR = old_base
        self.assertIn("ayni gun klasoru", status["shops"][1]["dayRootWarning"])


class LocalServer(unittest.TestCase):
    """Ana sunucu yanit vermezse (ya da 502/503/504) dukkanin yerel sunucusu."""

    def setUp(self):
        import stocktrack
        stocktrack._local_until.clear()
        FakeServer.calls = []
        FakeServer.posts = []
        FakeServer.requested = []
        FakeServer.jobs = []
        self.srv = HTTPServer(("127.0.0.1", 0), FakeServer)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.local = "http://127.0.0.1:%d/api/v1" % self.srv.server_port
        # Kapali port: baglanti reddedilir (ana sunucu yok).
        probe = HTTPServer(("127.0.0.1", 0), FakeServer)
        self.dead = "http://127.0.0.1:%d/api/v1" % probe.server_port
        probe.server_close()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_falls_back_and_prefers_local_for_a_while(self):
        api = StockTrack(self.dead, "k", timeout=2, fallback=self.local)
        self.assertEqual(api.ping(), "Acme Reklam")
        self.assertEqual(api.via, "yerel sunucu")
        api.report_folders("q1", {"host": "PC", "folder": "D:/x"})
        self.assertEqual(FakeServer.posts[-1][0], "/api/v1/corel/jobs/q1/folders")
        # yeni bir istemci (sonraki tur) once yerel sunucuya sorar
        api2 = StockTrack(self.dead, "k", timeout=2, fallback=self.local)
        self.assertEqual(api2._servers()[0], self.local)

    def test_real_rejection_is_not_hidden_by_the_local_server(self):
        api = StockTrack(self.local, "yanlis", timeout=2, fallback=self.local + "/x")
        with self.assertRaises(R.ServerError) as cm:
            api.ping()
        self.assertIn("401", str(cm.exception))

    def test_no_local_server_keeps_the_old_error(self):
        with self.assertRaises(R.ServerError) as cm:
            StockTrack(self.dead, "k", timeout=2).ping()
        self.assertIn("ulasilamiyor", str(cm.exception))

    def test_fallback_from_config_or_addon(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "c.json")
        with open(p, "w") as f:
            json.dump({}, f)
        self.assertEqual(Config(p, addon_reader=lambda: {"server2": "http://10.0.0.9/api/v1/"}).fallback(),
                         "http://10.0.0.9/api/v1")
        with open(p, "w") as f:
            json.dump({"fallback_server": "http://own/api/v1"}, f)
        self.assertEqual(Config(p, addon_reader=lambda: {"server2": "http://10.0.0.9/api/v1"}).fallback(),
                         "http://own/api/v1")


class AddonSettings(unittest.TestCase):
    """Corel eklentisinin kayit defteri ayarlari (Windows) bos alanlari doldurur."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def cfg(self, data, addon):
        p = os.path.join(self.dir, "c.json")
        with open(p, "w") as f:
            json.dump(data, f)
        return Config(p, addon_reader=lambda: dict(addon))

    def test_connection_from_addon_when_runner_config_is_empty(self):
        addon = {"server": "http://10.0.0.5/api/v1/", "api_key": "ak"}
        self.assertEqual(self.cfg({}, addon).connection(), ("http://10.0.0.5/api/v1", "ak", "Corel eklentisi"))
        # eski kurulumlardaki ornek adres bos sayilir
        self.assertEqual(self.cfg({"server": "http://192.168.1.50/api/v1", "api_key": "own"}, addon).connection()[0],
                         "http://10.0.0.5/api/v1")
        # runner'in kendi degeri once gelir
        self.assertEqual(self.cfg({"server": "http://x/api/v1", "api_key": "own"}, addon).connection(),
                         ("http://x/api/v1", "own", "runner config.json"))

    def test_day_root_precedence_matches_the_add_on(self):
        rc = os.path.join(self.dir, "renamer.json")
        with open(rc, "w") as f:
            json.dump({"daily_folders": {"enabled": False, "base_dir": "C:\\Masaustu\\Gunluk",
                                         "date_format": "%d.%m.%Y", "separator": "_"}}, f)
        base = {"day_folders": {"base_dir": "", "renamer_config": rc}}
        rule = self.cfg(base, {"day_root": "D:\\Isler\\"}).day_rule()
        self.assertEqual((rule["base_dir"], rule["source"], rule["date_format"]), ("D:\\Isler", "Corel eklentisi", "%d.%m.%Y"))
        rule = self.cfg(base, {}).day_rule()
        self.assertEqual(rule["source"], "CDR Auto Renamer")
        self.assertIn("kapali", rule["warning"])
        own = {"day_folders": {"base_dir": "E:\\Is", "renamer_config": rc}}
        rule = self.cfg(own, {"day_root": "D:\\Isler"}).day_rule()
        self.assertEqual((rule["base_dir"], rule["date_format"]), ("E:\\Is", "%d-%m-%Y"))

    def test_separator_and_long_sheet_from_addon(self):
        cfg = self.cfg({}, {"separator": "__", "long_mm": "3500"})
        self.assertEqual((cfg.group_separator(), cfg.long_sheet_mm()), ("__", 3500.0))
        cfg = self.cfg({"group_separator": "--", "long_sheet_mm": 4000}, {"separator": "__", "long_mm": "3500"})
        self.assertEqual((cfg.group_separator(), cfg.long_sheet_mm()), ("--", 4000.0))
        cfg = self.cfg({}, {})
        self.assertEqual((cfg.group_separator(), cfg.long_sheet_mm()), ("--", 4000.0))


if __name__ == "__main__":
    unittest.main()
