# GÖREV G — Faz 1'in düzeltme sonrası 5-koşum ölçümü (H1'den beri aranan)

**Tarih:** 2026-09-04 · **Kod/config değişikliği: YOK** (yalnızca ölçüm)
**Koşumlar:** f1–f5, her birinde tam SITL yeniden başlatma

---

## SONUÇ: **Faz 1 başarısı 0/5** — ve nedeni artık TEK BİR ÖLÇÜLMÜŞ SAYI

| koşum | Görev 2 | Faz 1 sonucu | deneme | en derin insertion | **gereken salım** | kalib. | rap. irtifa |
|---|---|---|---|---|---|---|---|
| f1 | 2/2 | FAIL#3 (Ö3 doyum) | **1** | −159.5 mm | **0.488 m** | 0.69× | 0.90 |
| f2 | 2/2 | FAIL#3 (Ö3 doyum) | **1** | −93.9 mm | **0.422 m** | 2.58× | 0.95 |
| f3 | 2/2 | FAIL#3 (Ö3 doyum) | **1** | −61.8 mm | **0.390 m** | 1.42× | 0.90 |
| f4 | 2/2 | FAIL#3 (Ö3 doyum) | **1** | −137.8 mm | **0.466 m** | 1.07× | 0.89 |
| f5 | 2/2 | FAIL#3 (Ö3 doyum) | **1** | −111.9 mm | **0.441 m** | 2.75× | 0.90 |

**5/5 aynı yerde ve aynı nedenle:** kancanın yuvaya erişmesi için gereken
salım **0.390–0.488 m**, vincin fiziksel sınırı **0.350 m**.
**Açık 40–138 mm.**

Faz 1 bu düzenekte **yapısal olarak imkânsız.** Bu bir ayar ya da
zamanlama sorunu değil; kanca fiziksel olarak yetişemiyor.

### Ö3 doyum koruması 5/5 çalıştı

Her koşumda **1 deneme yapıldı, 2 atlandı**. Önceden koşum başına
3 deneme × (12 s pencere + yeniden hizalama) yakılıyordu. Kazanç ölçüldü
ve gerekçe her koşumda `aborted.needed_payout_m` olarak sayıyla kayıtlı.

---

## 1 · Görev 2 regresyonu — n=8 ile kesinleşti (BOZULMA YOK)

Önceki rapor n=3 ile "bozulma yok" demişti; d1–d3 + f1–f5 ile n=8:

| | n | min | ortanca | max | **ortalama** |
|---|---|---|---|---|---|
| ÖNCE `MAVI_ALTIGEN` | 11 | 0.020 | 0.110 | 0.181 | 0.123 |
| **SONRA** `MAVI_ALTIGEN` | 8 | 0.018 | **0.095** | 0.161 | **0.085** |
| ÖNCE `KIRMIZI_UCGEN` | 11 | 0.155 | 0.273 | 0.398 | 0.266 |
| **SONRA** `KIRMIZI_UCGEN` | 8 | 0.053 | **0.274** | 0.393 | **0.246** |

**İkisi de iyileşti**, `MAVI_ALTIGEN` belirgin (ortalama 0.123 → 0.085).
Bir önceki raporda `KIRMIZI_UCGEN` ortalaması n=3 ile kötüleşmiş
görünüyordu (0.302); n=8 ile **0.246**, yani o **örneklem gürültüsüydü**.

---

## 2 · Kalibrasyon oranı — DÜZELTME, tam örneklemle

> ⚠️ Bir önceki rapor (§3) bu oranı **n=2** ile verdi (1.02× / 1.68×) ve
> tabloyu olduğundan iyi gösterdi. Tam örneklem aşağıdadır.

| | n | min | ortanca | max | **yayılım** |
|---|---|---|---|---|---|
| ÖNCE | 4 | 0.15× | 0.48× | 3.43× | **23.1 kat** |
| **SONRA** | **7** | **0.69×** | **1.42×** | **2.75×** | **4.0 kat** |

**İyileşme gerçek ama n=2'nin gösterdiği kadar temiz değil:** oran 1'e
yaklaştı ve yayılım 23 kattan 4 kata indi, ancak hâlâ 0.69–2.75 arasında
saçılıyor. Yani datum düzeltmesi bu sapmanın **büyük kısmını** açıklıyor,
**tamamını değil** — geriye kalan, ölçülen EKF↔gerçek farkı (0.12 m) ve
sarkaç salınımı olabilir. **Kapatılmadı.**

Görüntü tahmininin kendisi de toparlandı: yayılım **6.1 cm → 2.7 cm**.

### En güçlü işaret: raporlanan irtifa

`[HIZA_KALIBRASYON]` satırındaki irtifa, komut `HOOK_VISUAL_ALIGN_ALTITUDE_M = 0.90`:

| | değerler | ortalama | komuttan fark |
|---|---|---|---|
| ÖNCE | 0.70, 0.71, 0.70, 0.71 | 0.705 | **−0.195 m** |
| **SONRA** | 0.90, 0.89, 0.90, 0.95, 0.90, 0.89, 0.90 | **0.904** | **+0.004 m** |

**0.195 m'lik sistematik fark 4 mm'ye indi.** Ölçülen datum kaymasıyla
(0.177 m) aynı mertebede ve **7/7 koşumda tutarlı.** Bu, teşhisin en
temiz bağımsız doğrulaması.

---

## 3 · Kalan açık — nerede olduğu artık kesin

| bileşen | büyüklük | düzeltilebilir mi |
|---|---|---|
| datum kayması (`ref_alt` ↔ `home.alt`) | 0.177 m | ✅ **düzeltildi** (`3c816f8f`) |
| EKF ↔ gerçek kestirim hatası | 0.121 m | ❌ telemetri katmanında değil |
| geriye kalan erişim açığı | **0.040–0.138 m** | — |

Gereken salım (0.390–0.488) ile sınır (0.350) arasındaki açık, ölçülen
EKF hatasıyla **aynı mertebede.** Yani datum kapandı; Faz 1'i açan şey
artık **kestirim doğruluğu ya da fiziksel geometri.**

**Üç olası yön (hiçbiri ölçülmedi, öneri değil — seçenek):**
1. **Kestirimi düzelt** — EKF'in 0.12 m eksik okumasının kaynağı
   (E4a'da `EKF2_OF_CTRL` kapatılmıştı; baro/GPS dikey füzyonu incelenmeli).
2. **Geometriyi değiştir** — `HookRopeJoint` üst limiti 0.35 m; SDF'de
   yorumu "0.50 → 0.35, çünkü fazla salım kordu katlıyor" diyor. Sınırı
   yükseltmek katlanma sorununu geri getirir.
3. **Aracı daha alçağa indir** — `GOREV3_DESCENT_ALTITUDE_M` 0.30 → daha
   düşük. Artık okuma doğru olduğu için bu güvenli biçimde denenebilir;
   0.30 komutu bugün gerçekte ~0.42 m demek.

---

## 4 · Kapsam ve dürüstlük

- Faz 1: **5/5 aynı sonuç**, tek örnekten genelleme yok.
- Görev 2 regresyonu: n=8 (sonra) vs n=11 (önce).
- Kalibrasyon: **n=7**; bir önceki raporun n=2'lik tablosu bu belgeyle
  düzeltildi.
- `−down_m == −local.z` eşitliği hâlâ ayrıca ölçülmedi; §2'deki irtifa
  örtüşmesi (0.904 vs komut 0.900) güçlü dolaylı kanıt.
- §3'teki üç yön **ölçülmedi**, seçenek olarak listelendi.
- Eşik envanteri (`gorevG-O5-duzeltme-regresyon.md` §4) hâlâ **kontrol
  edilmedi** — ayrı tur.
