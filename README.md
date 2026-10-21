# StockTrack Runner

StockTrack'te bir teklif **işe dönüştürülünce** (*Satış/İşlemeye Dönüştür*)
dükkân bilgisayarında klasörleri kendiliğinden açar. Teklif **oluşturulunca
klasör açılmaz**; teklif kabul edilip işe dönünce açılır. Corel eklentisini
(ac2f pack, `ac2fJob`) açmanıza gerek kalmaz; klasör adları eklentiyle
birebir aynıdır, ikisi aynı klasörleri tanır.

```
<gün klasörü>\<müşteri>\001-pleksi-1220x2440--2pcs--2800um-akpolimer-dokme-beyaz\001
                                                                               \002
                        002-pleksi-1220x1440--1pcs--2800um-akpolimer-dokme-siyah\001
                                                                               ሠx900
                        003-aluminyum-kompozit-1500x5000--1pcs--4000um-alucobond-gumus\001\p001
                                                                                          \p002
```

## Ne yapar

Teklif işe dönüştürüldükten en geç `poll_seconds` (30 sn) sonra:

1. **Müşteri klasörü**: firma adı varsa o, yoksa kişi adı; küçük harf,
   boşluksuz (`ozturk-reklam-ltd-sti`).
   - Teklifin verildiği günden dönüşüm gününe kadar müşterinin bir
     klasörü varsa (teklif 22'sinde verildi, export o günün klasörüne
     yazıldı, iş 25'inde dönüştü) **o klasör** kullanılır. Yoksa dönüşüm
     gününün klasörü altında yeni müşteri klasörü açılır.
   - `Ozturk Reklam Ltd. Sti` gibi eski (boşluklu) adla açılmış klasörler
     de tanınır.
2. **Takım yolu klasörleri**: teklifteki her tabaka kalemi için
   `001-<tür>-<en>x<boy>--<adet>pcs--<kalınlık>um-<marka>-<varyant>-<renk>`.
   - Ölçü, tabakanın **dönüşümden önceki** ölçüsüdür (dönüşüm plakanın
     kalan boyunu düşürür; StockTrack o anki ölçüyü teklif kalemine yazar).
   - Aynı tür/ebat/kalınlık/marka/varyant/renk **istiflenir**: klasör
     zaten varsa (eklentinin açtığı da olur) `--2pcs--` → `--3pcs--` olur
     ve `003` eklenir. Farklı olan sıradaki numarayla açılır.
   - Tabaka adedi kullanılan alandan hesaplanır: tam tabaka kaleminde
     adet kadar; 3 × 300×400 parça tek tabakaya sığar.
   - Boyu 4000 mm'den uzun tabakaların her `001`, `002` klasörüne `p001`,
     `p002` açılır.
3. **Kullanılan parça**: tabakanın bir kısmı kullanıldıysa grup klasörüne
   `u1220x900` dosyası (eklentinin *Used parts* işiyle aynı). Dosya
   zaten varsa dokunulmaz.
4. Müşteri klasörüne gizli bir `.stocktrack\<teklif>.done` işareti bırakır.
   Aynı teklif bir daha işlenmez — runner yeniden kurulsa ya da aynı ağ
   klasörünü iki bilgisayar paylaşsa bile.

Sunucuya ulaşılamazsa bekler; bağlantı gelince aradaki dönüşümleri sırayla
işler. İlk çalıştırmada **o günün başından** başlar (geçmiş bütün işler için
klasör açmaz).

## Çalışıyor mu?

Üç yerden görülür:

1. **Dükkân bilgisayarında:** masaüstündeki **StockTrack Runner Durumu**
   penceresi. Yeşil: çalışıyor ve StockTrack'e bağlı. Sarı: çalışıyor ama bir
   sorun var (ne olduğu "Son hata" satırında). Kırmızı: çalışmıyor → **Başlat**.
   Sunucu, dükkân, gün klasörü (ve bu bilginin nereden geldiği), son açılan
   klasörler (çift tıkla açılır). *Şimdi bak* runner'ın beklemeden bakmasını
   sağlar; *Bağlantıyı dene* bütün ayarları sınar.
2. **StockTrack › Ayarlar › Corel entegrasyonu › Otomatik klasörler:** her
   bilgisayar için bağlı / bağlantı yok, son nabız, gün klasörü, son açılan
   klasör, varsa sorun.
3. **StockTrack › Teklifler:** başlıkta "Runner bağlı · BILGISAYAR" rozeti;
   işe dönmüş her teklifte "📁 Klasörler açıldı: gün › müşteri" ya da neden
   açılmadığı. Runner kapalıyken dönen teklif için **Klasörleri yeniden iste**.

Komut satırından: `python runner.py --status` (çalışıyor mu, son klasörler,
son hata), `python runner.py --check` (ayarlar ve bağlantı).

## Kurulum

Gereken: Windows, [Python 3](https://www.python.org/downloads/) (kurulumda
**"Add python.exe to PATH"** işaretli). Ek paket gerekmez.

1. Bu klasörü indirin, `install.bat`'a çift tıklayın.
2. Corel eklentisinde (*Job setup*) sunucu adresi ve anahtar kayıtlıysa
   hiçbir şey sorulmaz; runner eklentidekini kullanır (eklentide
   değiştirirseniz runner da izler). Kayıtlı değilse StockTrack › **Ayarlar ›
   Corel entegrasyonu** sayfasındaki **sunucu adresini** ve **anahtarı**
   girin (anahtar hangi dükkânınsa o dükkânın teklifleri gelir).
3. Kurulum bağlantıyı dener, Windows açılışına kısayol koyar, masaüstüne
   **StockTrack Runner Durumu** kısayolunu koyar, runner'ı arka planda
   başlatır, ilk turdan sonra durumu yazar ve durum penceresini açar.

Güncellemek için yeni sürümle `install.bat`'ı yeniden çalıştırın (ayarlar
korunur).

Program `%LOCALAPPDATA%\StockTrackRunner` klasörüne kurulur. Kaldırmak için
`uninstall.bat`.

## Gün klasörü

Corel eklentisiyle aynı öncelikle bulunur:

1. runner `config.json`'daki `day_folders.base_dir` (doluysa),
2. Corel eklentisinin **gün klasörü kökü** ayarı (*Job setup*),
3. **CDR Auto Renamer**'ın ayar dosyası
   (`%LOCALAPPDATA%\CdrAutoRenamer\config.json` → `daily_folders.base_dir`).

Tarih biçimi ve ayraç CDR Auto Renamer'dan gelir; gün klasörü yoksa aynı
adla açılır (`18-10-2026--pazar`). Hangisinin kullanıldığı durum penceresinde
ve `--check` çıktısında "kaynak" olarak yazar. CDR Auto Renamer'da günlük
klasörler kapalıysa onun varsayılan yolu (Masaüstü\GunlukKlasorler) yanlış
olabilir; pencere bunu uyarı olarak gösterir.

## Ayarlar (`config.json`)

Kaydettiğiniz anda geçerli olur, yeniden başlatmak gerekmez.

| Alan | Açıklama |
| --- | --- |
| `enabled` | `false` runner'ı durdurur (program açık kalır). |
| `server` | StockTrack adresi, `/api/v1` ile: `http://192.168.1.50/api/v1`, `https://stok.ornek.com/api/v1`. Boşsa Corel eklentisindeki |
| `api_key` | Dükkânın Corel anahtarı. Boşsa Corel eklentisindeki |
| `fallback_server` | Dükkândaki **yerel StockTrack sunucusu** (replika), `/api/v1` ile. Ana sunucu cevap vermezse (ya da 502/503/504) runner ona bağlanır; 5 dakika önce ona sorar. Boşsa Corel eklentisinin *Local srv* (Job setup `5`) ayarı. |
| `poll_seconds` | Kaç saniyede bir bakılacağı (varsayılan 30) |
| `day_folders.base_dir` | Boşsa CDR Auto Renamer'ınki; doluysa bu dizin ve aşağıdaki biçim |
| `day_folders.renamer_config` | CDR Auto Renamer'ın ayar dosyası |
| `day_folders.date_format`, `separator` | `base_dir` doluyken gün klasörü adı: `%d-%m-%Y` + `--` + gün |
| `group_separator` | Klasör adındaki ayraç; boşsa eklentinin ayarı, o da yoksa `--` |
| `long_sheet_mm` | Bundan uzun tabakaya `p001`/`p002`; boşsa eklentinin *Long sheet* ayarı, o da yoksa 4000 (0 bölmez) |
| `open_explorer` | `true` ise açılan müşteri klasörü Gezgin'de açılır |

## Denetim ve günlük

```
python %LOCALAPPDATA%\StockTrackRunner\runner.py --status  # çalışıyor mu, son klasörler, son hata
python %LOCALAPPDATA%\StockTrackRunner\runner.py --check   # ayar, gün klasörü, sunucu
python %LOCALAPPDATA%\StockTrackRunner\runner.py --once    # bekleyenleri bir kez işle
```

Her açılan klasör `%LOCALAPPDATA%\StockTrackRunner\runner.log`'a yazılır;
anlık durum `status.json`'dadır. Runner her turda StockTrack'e nabız gönderir
ve açtığı müşteri klasörünü teklife bildirir.

### Klasör açılmadıysa

| Görülen | Neden / çözüm |
| --- | --- |
| Teklifte "işe dönüştürülünce açılır" | Teklif henüz işe dönmedi. Kabul edip *Satış/İşlemeye Dönüştür*. |
| "Runner kurulmadı" / "bağlı değil" | Bilgisayar kapalı, runner durmuş ya da hiç bağlanamadı: durum penceresinde **Başlat**, sonra *Bağlantıyı dene*. |
| Sorun: "anahtar geçersiz" | StockTrack'te yeni anahtar üretildi: eklentiye (ya da `config.json`'a) yenisini yazın. |
| Sorun: "Gün klasörü bilinmiyor" | Corel eklentisinde gün klasörü kökünü ya da `config.json`'da `day_folders.base_dir`'i yazın. |
| Sorun: "uç bulunamadı" | StockTrack sunucusu eski: son sürüme güncelleyin. |
| Durumda "ana sunucu yanıt vermiyor; yerel sunucu kullanılıyor" | İnternet ya da merkez gitmiş; runner dükkândaki yerel sunucuyla çalışıyor. Klasör bildirimleri yerel sunucuda tutulur, bağlantı gelince merkeze aktarılır. |
| Klasör başka yerde açılmış | Durum penceresinde gün klasörünün *kaynağına* bakın; doğrusunu eklentide ya da `config.json`'da yazın, sonra teklifte **Klasörleri yeniden iste**. |

## Corel eklentisiyle birlikte

- **Export DXF** (iş menüsü 3) runner'ın açtığı müşteri klasörüne yazar.
- Runner'ın klasör açtığı bir iş için **Toolpath folders**'ı (iş menüsü 4)
  ayrıca çalıştırmayın: tabakaları ikinci kez istifler. Eklenti 1.17.1'den
  itibaren müşteri klasöründe runner'ın işaretini görürse onay penceresinde
  uyarır. Teklifsiz işlerde iş menüsü 4 eskisi gibi kullanılır.
- **Used parts** (iş menüsü 5) aynı dosyaları yazar; runner yazdıysa
  dokunmaz, iki kez çalışması zarar vermez.

## Geliştirme

```
python -m unittest discover -s tests
```

Testler klasör adlarını, istiflemeyi, uzun tabakayı, kullanılan parça
dosyasını, eski adlı müşteri klasörünü, gün seçimini, aynı teklifin bir
kez işlenmesini, nabzı, klasör bildirimini, yeniden istenen teklifi ve
Corel eklentisi ayarlarının önceliğini (sahte bir StockTrack sunucusuyla)
dener.
