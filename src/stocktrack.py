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
        req = urllib.request.Request(url, headers={
            "X-Api-Key": self.api_key,
            "Accept": "application/json, text/plain",
            "User-Agent": "stock-track-runner",
        })
        try:
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
            raise ServerError("HTTP %s: %s" % (exc.code, msg))
        except (urllib.error.URLError, OSError) as exc:
            raise ServerError("sunucuya ulasilamiyor: %s" % getattr(exc, "reason", exc))

    def ping(self):
        """Isletme adi (eklentinin baglanti denemesiyle ayni uc)."""
        lines = [l for l in self._get("/corel/ping").splitlines() if l and not l.startswith("#")]
        parts = lines[0].split("\t") if lines else []
        return parts[1] if len(parts) > 1 else ""

    def jobs(self, since=None, limit=50):
        """Bu andan (dahil) sonra ise donusturulen teklifler, eskiden yeniye."""
        body = json.loads(self._get("/corel/jobs", {"since": since, "limit": limit}))
        if isinstance(body, dict) and "data" in body:
            body = body["data"]
        if not isinstance(body, list):
            raise ServerError("beklenmeyen yanit")
        return body
