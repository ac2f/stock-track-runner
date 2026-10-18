# StockTrack Runner

StockTrack'te bir teklif **işe dönüştürülünce** (*Satış/İşlemeye Dönüştür*)
dükkân bilgisayarında klasörleri kendiliğinden açar. Corel eklentisini
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

## Kurulum

Gereken: Windows, [Python 3](https://www.python.org/downloads/) (kurulumda
**"Add python.exe to PATH"** işaretli). Ek paket gerekmez.

1. Bu klasörü indirin, `install.bat`'a çift tıklayın.
2. Sorulduğunda StockTrack › **Ayarlar › Corel entegrasyonu** sayfasındaki
   **sunucu adresini** ve **anahtarı** girin (Corel eklentisine girilenlerin
   aynısı; anahtar hangi dükkânınsa o dükkânın teklifleri gelir).
3. Kurulum bağlantıyı dener, Windows açılışına kısayol koyar ve runner'ı
   arka planda başlatır.

Program `%LOCALAPPDATA%\StockTrackRunner` klasörüne kurulur. Kaldırmak için
`uninstall.bat`.

## Gün klasörü

Varsayılan olarak **CDR Auto Renamer**'ın ayar dosyası okunur
(`%LOCALAPPDATA%\CdrAutoRenamer\config.json` → `daily_folders`): ana dizin,
tarih biçimi ve ayraç oradan gelir, iki program aynı klasörü kullanır. Gün
klasörü yoksa aynı adla açılır (`18-10-2026--pazar`).

CDR Auto Renamer kullanmıyorsanız `config.json`'da `day_folders.base_dir`
yazın.

## Ayarlar (`config.json`)

Kaydettiğiniz anda geçerli olur, yeniden başlatmak gerekmez.

| Alan | Açıklama |
| --- | --- |
| `enabled` | `false` runner'ı durdurur (program açık kalır). |
| `server` | StockTrack adresi, `/api/v1` ile: `http://192.168.1.50/api/v1`, `https://stok.ornek.com/api/v1` |
| `api_key` | Dükkânın Corel anahtarı |
| `poll_seconds` | Kaç saniyede bir bakılacağı (varsayılan 30) |
| `day_folders.base_dir` | Boşsa CDR Auto Renamer'ınki; doluysa bu dizin ve aşağıdaki biçim |
| `day_folders.renamer_config` | CDR Auto Renamer'ın ayar dosyası |
| `day_folders.date_format`, `separator` | `base_dir` doluyken gün klasörü adı: `%d-%m-%Y` + `--` + gün |
| `group_separator` | Klasör adındaki ayraç (eklentinin Job setup › 4 ayarıyla aynı olmalı; varsayılan `--`) |
| `long_sheet_mm` | Bundan uzun tabakaya `p001`/`p002` (eklentinin *Long sheet* ayarı; 0 bölmez) |
| `open_explorer` | `true` ise açılan müşteri klasörü Gezgin'de açılır |

## Denetim ve günlük

```
python %LOCALAPPDATA%\StockTrackRunner\runner.py --check   # ayar, gün klasörü, sunucu
python %LOCALAPPDATA%\StockTrackRunner\runner.py --once    # bekleyenleri bir kez işle
```

Her açılan klasör `%LOCALAPPDATA%\StockTrackRunner\runner.log`'a yazılır.

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
dosyasını, eski adlı müşteri klasörünü, gün seçimini ve aynı teklifin bir
kez işlenmesini (sahte bir StockTrack sunucusuyla) dener.
