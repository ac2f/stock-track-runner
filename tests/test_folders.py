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
        report, problems = F.make_groups(self.cust, plan, header="Quote TKF-2026-0007  2026-10-17\n")
        self.assertEqual(problems, [])
        t = tree(self.cust)
        self.assertIn("001-pleksi-1220x2440--3pcs--2800um-akpolimer-dokme-beyaz/003", t)
        self.assertNotIn("001-pleksi-1220x2440--3pcs--2800um-akpolimer-dokme-beyaz/004", t)
        self.assertIn("002-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-siyah/001", t)
        self.assertIn("002-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-siyah/u1220x900", t)
        self.assertIn("003-aluminyum-kompozit-1500x5000--1pcs--4000um-alucobond-gumus/001/p002", t)
        self.assertNotIn("003-aluminyum-kompozit-1500x5000--1pcs--4000um-alucobond-gumus/001/p003", t)
        with open(os.path.join(self.cust, "002-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-siyah",
                               "u1220x900"), encoding="utf-8") as f:
            body = f.read()
        self.assertIn("Quote TKF-2026-0007", body)
        self.assertIn("Used 1220 x 900 mm of the 1220 x 2440 mm sheet", body)

    def test_stacks_onto_folders_the_add_on_made(self):
        os.makedirs(os.path.join(self.cust, "001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz", "002"))
        os.makedirs(os.path.join(self.cust, "004-dekota-1560x3050--1pcs--5000um", "001"))
        open(os.path.join(self.cust, "exp01--pleksi.dxf"), "w").close()
        F.make_groups(self.cust, F.plan_groups([sheet(quantity=1), sheet(color="mavi")]))
        t = tree(self.cust)
        self.assertIn("001-pleksi-1220x2440--3pcs--2800um-akpolimer-dokme-beyaz/003", t)
        self.assertIn("005-pleksi-1220x2440--1pcs--2800um-akpolimer-dokme-mavi/001", t)
        self.assertIn("exp01--pleksi.dxf", t)

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


class FakeServer(BaseHTTPRequestHandler):
    jobs = []
    calls = []

    def do_GET(self):
        FakeServer.calls.append((self.path, self.headers.get("X-Api-Key")))
        if self.headers.get("X-Api-Key") != "k":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"message":"Gecersiz anahtar"}')
            return
        if self.path.startswith("/api/v1/corel/ping"):
            body = b"#ac2f-corel 1\nok\tAcme Reklam\n"
        else:
            body = json.dumps({"success": True, "data": FakeServer.jobs}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class Poll(unittest.TestCase):
    def setUp(self):
        FakeServer.calls = []
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
        self.assertIn(day + "/ozturk-reklam/001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz/002", t)
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


if __name__ == "__main__":
    unittest.main()
