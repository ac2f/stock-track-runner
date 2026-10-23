"""StockTrack Runner durum penceresi.

Masaüstündeki "StockTrack Runner Durumu" kısayolu bunu açar: runner çalışıyor
mu, StockTrack'e bağlı mı, hangi gün klasörüne yazıyor, en son hangi
tekliflerin klasörünü açtı, son hata ne. Buradan runner başlatılır, hemen
bakması istenir, bağlantı denenir, günlük ve ayar dosyası açılır.
"""
import contextlib
import io
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import runner as R  # noqa: E402
from config import Config  # noqa: E402
from status import ago, is_fresh, read_status, seconds_since  # noqa: E402

REFRESH_MS = 2000


def tr_ago(seconds):
    """status.ago() konsol için ASCII yazar; pencerede Türkçe harflerle."""
    return ago(seconds).replace(" once", " önce").replace("gun", "gün").replace("hic", "hiç")


def open_path(path):
    if not path:
        return
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: S606 (Windows)
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as exc:
        messagebox.showerror("Açılamadı", "%s\n\n%s" % (path, exc))


def pythonw():
    exe = sys.executable
    if os.name == "nt" and exe.lower().endswith("python.exe"):
        w = exe[:-len("python.exe")] + "pythonw.exe"
        if os.path.exists(w):
            return w
    return exe


def start_runner():
    script = os.path.join(BASE_DIR, "runner.py")
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([pythonw(), script], cwd=BASE_DIR, creationflags=flags, close_fds=True)
    else:
        subprocess.Popen([sys.executable, script], cwd=BASE_DIR, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_runner(pid):
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    else:
        try:
            os.kill(int(pid), 15)
        except OSError:
            pass


class StatusWindow:
    def __init__(self, root):
        self.root = root
        root.title("StockTrack Runner Durumu")
        root.geometry("820x560")
        root.minsize(640, 420)
        pad = {"padx": 10, "pady": 3}

        top = ttk.Frame(root)
        top.pack(fill="x", padx=10, pady=(10, 4))
        self.dot = tk.Label(top, text="●", font=("Segoe UI", 22))
        self.dot.pack(side="left")
        self.headline = ttk.Label(top, text="…", font=("Segoe UI", 13, "bold"))
        self.headline.pack(side="left", padx=6)
        self.start_btn = ttk.Button(top, text="Başlat", command=self.on_start)
        self.start_btn.pack(side="right", padx=3)
        ttk.Button(top, text="Şimdi bak", command=self.on_poke).pack(side="right", padx=3)

        grid = ttk.Frame(root)
        grid.pack(fill="x", **pad)
        grid.columnconfigure(1, weight=1)
        self.values = {}
        rows = [
            ("server", "Sunucu"),
            ("shop", "Dükkân"),
            ("day", "Gün klasörü"),
            ("today", "Bugün"),
            ("warning", "Uyarı"),
            ("error", "Son hata"),
        ]
        for i, (key, label) in enumerate(rows):
            ttk.Label(grid, text=label + ":", font=("Segoe UI", 10, "bold")).grid(row=i, column=0, sticky="nw", pady=2)
            var = ttk.Label(grid, text="—", wraplength=600, justify="left")
            var.grid(row=i, column=1, sticky="w", pady=2)
            self.values[key] = var
        ttk.Button(grid, text="Aç", width=5, command=lambda: open_path(self.status.get("today") or self.status.get("dayRoot"))).grid(row=3, column=2, sticky="e")

        ttk.Label(root, text="Son açılan klasörler (çift tıkla: klasörü aç)", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        cols = ("quote", "customer", "at", "folder")
        self.tree = ttk.Treeview(root, columns=cols, show="headings", height=8)
        for c, title, w in (("quote", "Teklif", 115), ("customer", "Müşteri", 170), ("at", "Zaman", 135), ("folder", "Klasör", 370)):
            self.tree.heading(c, text=title)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10)
        self.tree.bind("<Double-1>", self.on_open_row)
        self.empty_hint = ttk.Label(root, text="", foreground="#666")
        self.empty_hint.pack(anchor="w", padx=10)

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", padx=10, pady=10)
        ttk.Button(bottom, text="Bağlantıyı dene", command=self.on_check).pack(side="left", padx=3)
        ttk.Button(bottom, text="Günlüğü aç", command=lambda: open_path(os.path.join(BASE_DIR, "runner.log"))).pack(side="left", padx=3)
        ttk.Button(bottom, text="Ayarları aç", command=lambda: open_path(R.CONFIG_PATH)).pack(side="left", padx=3)
        ttk.Button(bottom, text="Kapat", command=root.destroy).pack(side="right", padx=3)
        self.version = ttk.Label(bottom, text="", foreground="#888")
        self.version.pack(side="right", padx=10)

        self.status = {}
        self.running = False
        self.refresh()

    # ── yenileme ──────────────────────────────────────────────────────
    def refresh(self):
        self.status = read_status(R.STATUS_PATH)
        self.running = R.lock_held()
        s = self.status
        fresh = is_fresh(s, self.running)
        last = tr_ago(seconds_since(s.get("lastLoopAt")))
        if fresh and not s.get("error"):
            color, text = "#16a34a", "Çalışıyor ve bağlı — son kontrol %s" % last
        elif fresh:
            color, text = "#d97706", "Çalışıyor ama bir sorun var — son kontrol %s" % last
        elif self.running:
            color, text = "#d97706", "Çalışıyor ama son kontrol gecikti (%s)" % last
        else:
            color, text = "#dc2626", "Çalışmıyor"
        self.dot.configure(fg=color)
        self.headline.configure(text=text)
        self.start_btn.configure(text="Yeniden başlat" if self.running else "Başlat")

        conn = ""
        if s.get("server"):
            conn = "  ✓ bağlı" if s.get("connected") else "  ✗ bağlanamadı"
        self.values["server"].configure(text="%s%s   (kaynak: %s)" % (s.get("server") or "—", conn, s.get("serverSource") or "—"))
        shops = s.get("shops") or []
        if shops:
            # Bir bilgisayar birden çok dükkâna klasör açıyor: her dükkân ayrı satır.
            self.values["shop"].configure(text="\n".join(
                "%s  %s  (kod %s)" % (e.get("shopName") or e.get("name") or "?",
                                      "✓ bağlı" if e.get("connected") else "✗ bağlanamadı", e.get("folderCode") or "—")
                for e in shops))
            self.values["day"].configure(text="\n".join(
                "%s: %s   (kaynak: %s)" % (e.get("shopName") or e.get("name") or "?", e.get("dayRoot") or "BİLİNMİYOR",
                                           e.get("dayRootSource") or "—")
                for e in shops))
            warns = ["%s: %s" % (e.get("shopName") or e.get("name") or "?", w)
                     for e in shops for w in (e.get("dayRootWarning"), e.get("note")) if w]
        else:
            code = " (klasör kodu %s)" % s["folderCode"] if s.get("folderCode") else ""
            self.values["shop"].configure(text=(s.get("shopName") or "—") + code)
            self.values["day"].configure(text="%s   (kaynak: %s)" % (s.get("dayRoot") or "BİLİNMİYOR", s.get("dayRootSource") or "—"))
            warns = [w for w in (s.get("dayRootWarning"), s.get("note")) if w]
        self.values["today"].configure(text=s.get("today") or "—")
        self.values["warning"].configure(text="\n".join(warns) or "—")
        self.values["error"].configure(text=s.get("error") or "yok", foreground="#dc2626" if s.get("error") else "")
        self.version.configure(text="Runner %s · %s" % (s.get("version") or R.VERSION, s.get("host") or R.HOST))

        self.tree.delete(*self.tree.get_children())
        for r in s.get("recent") or []:
            who = ("[%s] " % r["shop"] if shops and r.get("shop") else "") + (r.get("customer") or "")
            self.tree.insert("", "end", values=(r.get("quoteNo", ""), who,
                                                (r.get("at") or "")[:16].replace("T", " "), r.get("folder", "")))
        self.empty_hint.configure(
            text="" if s.get("recent") else
            "Henüz klasör açılmadı. Klasörler teklif StockTrack'te İŞE DÖNÜŞTÜRÜLÜNCE açılır (teklif oluşturulunca değil).")
        self.root.after(REFRESH_MS, self.refresh)

    # ── düğmeler ──────────────────────────────────────────────────────
    def on_open_row(self, _event):
        sel = self.tree.selection()
        if sel:
            open_path(self.tree.item(sel[0], "values")[3])

    def on_poke(self):
        if not self.running:
            messagebox.showinfo("Runner çalışmıyor", "Önce “Başlat” ile runner'ı çalıştırın.")
            return
        with open(R.POKE_PATH, "w") as f:
            f.write(str(time.time()))

    def on_start(self):
        if self.running:
            stop_runner(self.status.get("pid"))
            for _ in range(20):
                time.sleep(0.25)
                if not R.lock_held():
                    break
        start_runner()

    def on_check(self):
        win = tk.Toplevel(self.root)
        win.title("Bağlantı denemesi")
        win.geometry("760x380")
        text = tk.Text(win, wrap="word", font=("Consolas", 10))
        text.pack(fill="both", expand=True, padx=8, pady=8)
        text.insert("end", "Deneniyor…\n")

        def work():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    R.check(Config(R.CONFIG_PATH))
                except Exception as exc:  # pencere açık kalsın, hatayı göstersin
                    print("Hata: %s" % exc)
            out = buf.getvalue()
            self.root.after(0, lambda: (text.delete("1.0", "end"), text.insert("end", out)))

        threading.Thread(target=work, daemon=True).start()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if os.name == "nt" else "clam")
    except tk.TclError:
        pass
    StatusWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
