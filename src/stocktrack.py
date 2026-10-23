import json
import time
import urllib.error
import urllib.parse
import urllib.request

# Ana sunucu yanit vermeyip yerel sunucu (replika) yanit verince bu kadar
# sure once yerel sunucuya sorulur; her turda ana sunucunun zaman asimi
# beklenmez (Corel eklentisiyle ayni kural).
LOCAL_FIRST_SECONDS = 300
_local_until = {}


class ServerError(Exception):
    """Sunucuya ulasilamadi ya da istek reddedildi; bir sonraki turda
    yeniden denenir."""


class Unreachable(ServerError):
    """Sunucu yanit vermedi ya da onundeki gecit "kapali" dedi (502/503/504):
    varsa yerel sunucu denenir."""


class StockTrack:
    """StockTrack'in Corel uclari. Kimlik, dukkanin Ayarlar > Corel
    entegrasyonu'ndan alinan anahtardir (eklentiyle ayni anahtar); anahtar
    hangi dukkaninsa o dukkanin teklifleri gelir."""

    def __init__(self, server, api_key, timeout=20, fallback=None):
        self.server = (server or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout
        # Dukkandaki yerel sunucu (replika): ana sunucu yanit vermezse.
        self.fallback = (fallback or "").rstrip("/")
        if self.fallback == self.server:
            self.fallback = ""
        # Son yanit yerel sunucudan geldiyse "yerel sunucu", yoksa None.
        self.via = None

    def _servers(self):
        if self.fallback and time.time() < _local_until.get(self.fallback, 0):
            return [self.fallback, self.server]
        return [self.server] + ([self.fallback] if self.fallback else [])

    def _get(self, path, params=None):
        if params:
            path += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return self._request(path, self._headers())

    def _post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        return self._request(path, headers, data)

    def _request(self, path, headers, data=None):
        """Once ana sunucu (yerel sunucuya yeni gecildiyse once o); yanit
        vermeyen ya da "kapali" diyen atlanir. Gercek bir ret (anahtar
        gecersiz ...) yerel sunucuyla ortulmez."""
        if not self.server:
            raise ServerError("sunucu adresi yok: Corel eklentisinde ya da config.json'da server yazin")
        last = None
        for base in self._servers():
            try:
                body = self._send(base + path, headers, data)
            except Unreachable as exc:
                last = exc
                continue
            if base == self.fallback:
                self.via = "yerel sunucu"
                _local_until[self.fallback] = time.time() + LOCAL_FIRST_SECONDS
            else:
                self.via = None
                _local_until.pop(self.fallback, None)
            return body
        raise last

    def _headers(self):
        return {
            "X-Api-Key": self.api_key,
            "Accept": "application/json, text/plain",
            "User-Agent": "stock-track-runner",
        }

    def _send(self, url, headers, data=None):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return res.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            try:
                msg = json.loads(body).get("message") or body
            except ValueError:
                msg = body
            if exc.code in (401, 403):
                msg = "anahtar gecersiz ya da dukkan kapali (%s)" % msg
            elif exc.code == 404:
                msg = "uc bulunamadi; StockTrack sunucusu guncel degil olabilir (%s)" % msg
            if exc.code in (502, 503, 504):
                raise Unreachable("HTTP %s: sunucu su an kapali (%s)" % (exc.code, url))
            raise ServerError("HTTP %s: %s" % (exc.code, msg))
        except (urllib.error.URLError, OSError) as exc:
            raise Unreachable("sunucuya ulasilamiyor (%s): %s" % (url, getattr(exc, "reason", exc)))
        except ValueError as exc:
            # "192.168.1.50/api/v1" gibi http:// olmayan adres
            raise ServerError("sunucu adresi hatali (%s): http:// ya da https:// ile baslamali" % exc)

    def ping(self):
        """Isletme adi (eklentinin baglanti denemesiyle ayni uc)."""
        lines = [l for l in self._get("/corel/ping").splitlines() if l and not l.startswith("#")]
        parts = lines[0].split("\t") if lines else []
        return parts[1] if len(parts) > 1 else ""

    def folder_settings(self):
        """Dukkanin klasor olusturucu ayarlari (StockTrack > Ayarlar > Corel):
        {enabled, code, materialSaleFolders, dayRoot, shopName}. Eski sunucuda
        (uc yok) None."""
        try:
            text = self._get("/corel/folder-settings")
        except ServerError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        try:
            body = json.loads(text)
        except ValueError:
            return None
        if isinstance(body, dict) and "data" in body:
            body = body["data"]
        return body if isinstance(body, dict) else None

    def jobs(self, since=None, limit=50):
        """Bu andan (dahil) sonra ise donusturulen teklifler, eskiden yeniye."""
        return self._list(self._get("/corel/jobs", {"since": since, "limit": limit}))

    def requested_jobs(self):
        """Klasorleri StockTrack ekranindan yeniden istenen teklifler."""
        return self._list(self._get("/corel/jobs/requested"))

    def heartbeat(self, payload):
        """Nabiz: StockTrack ekraninda "runner bagli" gorunsun."""
        self._post("/corel/runner/heartbeat", payload)

    def report_folders(self, quote_id, payload):
        """Teklifin klasorleri acildi: StockTrack teklifte klasor yolunu gosterir."""
        self._post("/corel/jobs/%s/folders" % quote_id, payload)

    @staticmethod
    def _list(text):
        try:
            body = json.loads(text)
        except ValueError:
            raise ServerError("beklenmeyen yanit (sunucu guncel mi? /corel/jobs yok olabilir)")
        if isinstance(body, dict) and "data" in body:
            body = body["data"]
        if not isinstance(body, list):
            raise ServerError("beklenmeyen yanit")
        return body
