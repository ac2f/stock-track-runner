import json
import urllib.error
import urllib.parse
import urllib.request


class ServerError(Exception):
    """Sunucuya ulasilamadi ya da istek reddedildi; bir sonraki turda
    yeniden denenir."""


class StockTrack:
    """StockTrack'in Corel uclari. Kimlik, dukkanin Ayarlar > Corel
    entegrasyonu'ndan alinan anahtardir (eklentiyle ayni anahtar); anahtar
    hangi dukkaninsa o dukkanin teklifleri gelir."""

    def __init__(self, server, api_key, timeout=20):
        self.server = (server or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout

    def _get(self, path, params=None):
        url = self.server + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return self._send(url, self._headers())

    def _post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        return self._send(self.server + path, headers, data)

    def _headers(self):
        return {
            "X-Api-Key": self.api_key,
            "Accept": "application/json, text/plain",
            "User-Agent": "stock-track-runner",
        }

    def _send(self, url, headers, data=None):
        if not self.server:
            raise ServerError("sunucu adresi yok: Corel eklentisinde ya da config.json'da server yazin")
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
            raise ServerError("HTTP %s: %s" % (exc.code, msg))
        except (urllib.error.URLError, OSError) as exc:
            raise ServerError("sunucuya ulasilamiyor: %s" % getattr(exc, "reason", exc))
        except ValueError as exc:
            # "192.168.1.50/api/v1" gibi http:// olmayan adres
            raise ServerError("sunucu adresi hatali (%s): http:// ya da https:// ile baslamali" % exc)

    def ping(self):
        """Isletme adi (eklentinin baglanti denemesiyle ayni uc)."""
        lines = [l for l in self._get("/corel/ping").splitlines() if l and not l.startswith("#")]
        parts = lines[0].split("\t") if lines else []
        return parts[1] if len(parts) > 1 else ""

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
