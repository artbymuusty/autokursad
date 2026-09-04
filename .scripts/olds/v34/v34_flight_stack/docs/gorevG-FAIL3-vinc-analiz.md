# GÖREV G / TAKİP 2 — FAZ 1: FAIL#3 vinç–insertion arızası

**Tarih:** 2026-09-04 · **Tip:** analiz · **Kod/config değişikliği: YOK**
**Veri:** `docs/gorevG-H1-dogrulama.md`'nin 5 bağımsız koşumu (r1, r2b, r3b, r5b — FAIL#3 olan 4'ü)

---

## TEŞHİS (önce, tek cümle)

**Kontrolcü değil, simülasyon değil, ölçüm değil — ÇAĞRI ARGÜMANI.**

`extend_winch_for()` iki ayrı yerden **iki ayrı irtifa argümanıyla**
çağrılıyor. İkinci çağrı, birincisinden **daha küçük** bir salım hesaplıyor
ve vinci **113–186 mm geri çekiyor** — tam da kancanın en aşağıda olması
gereken anda. `insertion` bu geri çekilme kadar, **1:1 oranında** bozuluyor.

---

## 1 · Sorulan üç ihtimalin elenmesi

### ❌ "Vinç kontrolcüsü komutu gönderiyor ama motor yanıt vermiyor"

**Yanlış. Vinç komutu 3 mm içinde takip ediyor ve ~1.4 s'de oturuyor.**

`seat_trace` `winch_m` zaman serisi (r2b, deneme 1; komut 0.191 m):

| t (s) | 0.1 | 1.5 | 3.0 | 6.0 | 9.0 | 11.9 |
|---|---|---|---|---|---|---|
| winch_m | 0.3067 | **0.1935** | 0.1935 | 0.1934 | 0.1933 | 0.1933 |

Dört koşumun tamamında aynı: komut → ~1.4 s → **hedefe ±3 mm**, sonra sabit.

| koşum | komut | ulaşılan (kararlı) | hata |
|---|---|---|---|
| r1 | 0.138 | 0.1400 / 0.1357 | +2 / −2 mm |
| r2b | 0.191 | 0.1935 / 0.1891 | +3 / −2 mm |
| r3b | 0.127 | 0.1290 / 0.1247 | +2 / −2 mm |
| r5b | 0.124 | 0.1265 / 0.1219 | +3 / −2 mm |

### ❌ "Gazebo plugin / joint tanımı eksik veya yanlış"

**Yanlış.** Prizmatik eklem hem uzuyor hem çekiliyor, hız da makul
(0.113 m'yi ~1.4 s'de → ~0.08 m/s, SDF sınırı 0.5 m/s'in altında).
`/hook/winch/cmd` (`gz.msgs.Double`, `gz_payload_actuator.py:151`)
komutları eksiksiz uygulanıyor.

### ❌ "achieved_m yanlış okunuyor, vinç aslında uzuyor ama sensör görmüyor"

**Yanlış — ve bu benim önceki okumamdaki hataydı.** H1 raporunda
`winch_at_window_start.achieved_m = 0.0018` değerini "vinç uzamıyor" diye
okumuştum. O alan **pencerenin t≈0.1 s'indeki tek örnek**; eklem henüz
hareket etmemiş. Zaman serisi bakıldığında 1.4 s sonra 0.189 m'ye
çıkıyor. **Örnekleme anı kaynaklı bir görüntü, arıza değil.**
(H1 raporunun §5.1'i bu yönüyle düzeltilmelidir.)

---

## 2 · GERÇEK NEDEN: iki çağıran, iki farklı irtifa

### 2.1 Formül

`gz_payload_actuator.py:256-270`:
```python
payout = altitude_m - deck_height_m + HOOK_PAYOUT_CHAIN_OFFSET_M + margin_m
       = altitude_m - 0.070 + 0.060 + 0.040
       = altitude_m + 0.030
```
Dört koşumda **birebir** doğrulandı:

| koşum | `altitude_m` | formül | raporlanan `payout_m` |
|---|---|---|---|
| r1 | 0.108 | 0.138 | 0.138 ✓ |
| r2b | 0.161 | 0.191 | 0.191 ✓ |
| r3b | 0.097 | 0.127 | 0.127 ✓ |
| r5b | 0.094 | 0.124 | 0.124 ✓ |

### 2.2 İki çağıran, iki argüman

| # | çağıran | satır | argüman | değer | salım |
|---|---|---|---|---|---|
| 1 | görev katmanı | `gorev3_pickup.py:912` | `GOREV3_DESCENT_ALTITUDE_M` | **0.30 (NOMİNAL)** | **0.330 m** |
| 2 | aktüatör, her denemede | `gz_payload_actuator.py:1522` | `altitude_m=_pick_alt` | **0.094–0.161 (ÖLÇÜLEN)** | **0.124–0.191 m** |

Ölçülen `winch_m` pencere başında **0.3045–0.3128** — yani (1) numaralı
çağrının 0.330 m'si (sarkma payıyla). Sonra (2) devreye giriyor ve
**vinci geri çekiyor.**

### 2.3 Geri çekilme ile insertion 1:1 örtüşüyor

Deneme 1, t=0.1 s → t=1.5 s:

| koşum | Δvinç | Δinsertion | oran |
|---|---|---|---|
| r1 | **−164.2 mm** | **−164.6 mm** | **1.00** |
| r3b | **−177.2 mm** | **−177.8 mm** | **1.00** |
| r5b | −186.3 mm | −250.9 mm | 1.35 |
| r2b | −113.2 mm | −75.2 mm | 0.66 |

r1 ve r3b'de **milimetre düzeyinde birebir**. r2b/r5b'deki sapma, hareket
sırasındaki sarkaç salınımı (bu dosyanın kendi ölçtüğü periyot 0.831 s,
`gorev3_pickup.py:110`) — yön ve mertebe aynı.

**Nedensellik sadece korelasyon değil, mekanizma da açık:** ip boyu
kısalırsa kanca yukarı gider. Başka bir açıklama gerekmiyor.

### 2.4 Bu, 2026-08-31 birleştirmesinin yarım kalmış hâli

`extend_winch_for` docstring'i (`gz_payload_actuator.py:1432-1438`):

> *"SALIM HESABININ TEK KAYNAGI (2026-08-31). Onceden iki yerde
> hesaplaniyordu: gorev katmani inis oncesi **nominal** irtifadan, aktuator
> ise alma aninda **gercek** irtifadan. **Ikisi de dogruydu** ama iki ayri
> cagri hook_payout_m'i ayri ayri cagiriyordu… Artik her iki cagiran da
> buradan gecer."*

O düzeltme **formülü** birleştirdi, **argümanı** birleştirmedi. Ve
"ikisi de doğruydu" **artık doğru değil**: ikinci çağrı bir *salım* değil,
bir *geri çekme* üretiyor. Refactor, düzeltmeye çalıştığı çift-hesaplamayı
tek fonksiyona taşıdı ama çelişkiyi çağrı yerinde bıraktı.

---

## 3 · İkinci, bağımsız eksiklik: salım en iyi hâlinde bile yetmiyor

Geri çekilme **öncesinde**, yani 0.30 m'lik salımdayken bile insertion
zaten kapının dışındaydı:

| koşum | t=0.1 s insertion | kapı |
|---|---|---|
| r1 | −84.0 mm | ≥ −4 mm |
| r2b | −104.1 mm | ≥ −4 mm |
| r3b | −100.3 mm | ≥ −4 mm |
| r5b | −171.6 mm | ≥ −4 mm |

Yani geri çekilmeyi düzeltmek **gerekli ama tek başına yeterli değil**:
en iyi durumda bile ~100 mm daha salım gerekiyor. Gereken ~0.41 m,
`HOOK_WINCH_MAX_EXTENSION_M = 0.35` ve `HOOK_WINCH_EXTEND_M = 0.40`
(`gz_payload_actuator.py:160,212`) — yani **fiziksel sınırın da üstünde.**

Bu, dosyanın kendi kaydettiği tartışmalı sabitle uyumlu
(`gz_payload_actuator.py:1455-1463`):

> *"Fiziksel erisim tavani AYRI bir sayi ve CHAIN_OFFSET'e bagli; o sabit
> su an tartismali — **SDF geometrisi 0.04236, kayitli kalibrasyon 0.060**
> — bu yuzden burada kasten yazilmiyor."*

`HOOK_PAYOUT_CHAIN_OFFSET_M = 0.060` (`:191`) formülde doğrudan yer alıyor.
Doğru değer daha büyükse salım da o kadar artar. **Bu sabit ölçülmeli.**

---

## 4 · Vinç SITL'e mi özgü — G5 ile ilişkisi

**Evet, tamamen simülasyona özgü.** `real_payload_actuator.py`'de
**"winch/vinç" kelimesi hiç geçmiyor**; gerçek donanımda vinç kavramı yok.

| katman | mekanizma |
|---|---|
| SITL (`GzPayloadActuator`) | `/hook/winch/cmd` prizmatik eklem + `HookAttachSystem` fixed joint |
| Gerçek (`RealPayloadActuator:75-110`) | **THIRD MISSION SERVO** — gövde `TODO[DONANIM]`, log + `asyncio.sleep` yer tutucu |

Arayüz ortak: `IPayloadActuator.activate_pickup_mechanism(altitude_m,
deck_height_m, on_retry)` (`i_payload_actuator.py:22`).

**G5 ile ilişki — dikkatli olunmalı:** G5 "gerçek aktüatör no-op" diyordu ve
o hâlâ doğru. Ama buradaki arıza **G5'in kapsamında değil**: bu, SITL
aktüatörünün *kendi içindeki* bir çağrı hatası. **Gerçek donanımda vinç
olmadığı için bu spesifik hata oraya taşınmaz** — ancak `altitude_m`
argümanının nominal mi ölçülen mi olduğu **arayüz düzeyinde** aynı
belirsizliği taşıyor, yani gerçek servo yazıldığında aynı tuzağa
düşülebilir. Arayüz sözleşmesi netleştirilmeli.

---

## 5 · `[HIZA_KALIBRASYON]` sapması aynı kök nedeni paylaşıyor mu

**Hayır — ayrı sorun.** Üç bağımsız gerekçe:

1. **Farklı eksen.** Kalibrasyon **yanal** (lateral) hatayı karşılaştırıyor;
   FAIL#3 **dikey** (insertion). Ölçülen lateral zaten çoğunlukla kapı
   içinde (min 1.9 mm, kapı ~10.25 mm) — yani lateral Faz 1'i düşürmüyor.
2. **Farklı rejim.** `[HIZA_KALIBRASYON]` `gorev3_pickup.py:765`'te, vinç
   salımı ise `:912`'de. Yani kalibrasyon **vinç çekiliyken** (kanca
   gövdenin altında gergin asılı) ölçülüyor; oturma ise **vinç açıkken**.
3. **Farklı imza.** Insertion hatası **sistematik ve yönü sabit** (dördü de
   negatif, mertebe tutarlı). Kalibrasyon oranı **rastgele**: 0.29× / 2.1× /
   3.3× / 6.7×, ve **yönü bile sabit değil** (r2b'de görüntü büyük, diğer
   üçünde küçük).

**Ortak tema var, ortak kök neden yok:** ikisi de "ipin ucundaki kancanın
pozu kontrol edilmiyor" ailesinden. Ama FAIL#3, hiçbir sarkaç fiziği
gerektirmeden, düz bir argüman hatasıyla tam olarak açıklanıyor.
Kalibrasyon sapması ise açıklanmadı ve **ayrı bir ölçüm işi.**

---

## 6 · ÖNERİLEN DÜZELTME (uygulanmadı)

Öncelik sırasıyla. **Hiçbiri bu FAZ'da uygulanmadı.**

### Ö1 — Argüman çelişkisini kapat (küçük, doğrudan, ölçülmüş)
`activate_pickup_mechanism` her denemede salımı **yeniden hesaplamamalı**;
ya görev katmanının kurduğu salımı korumalı, ya da **yalnızca büyütmeli**
(`payout = max(mevcut_achieved, hesaplanan)`). Vinci alma anında geri
çekmek hiçbir durumda istenmiyor.
*Beklenen etki: insertion 113–186 mm iyileşir. Ölçülmüş, 1:1.*

### Ö2 — `HOOK_PAYOUT_CHAIN_OFFSET_M`'i ölç (Ö1'den bağımsız, gerekli)
SDF geometrisi 0.04236 mı, kalibrasyon 0.060 mı — kod bunu **tartışmalı**
diye kaydetmiş ve formülde kullanmaya devam ediyor. Ö1 uygulansa bile
kalan ~100 mm açık bu sabitten geliyor olabilir.
*Bu bir ÖLÇÜM işi, tahmin işi değil.*

### Ö3 — Erişim tavanını görünür kıl
Gereken salım ~0.41 m, sınır 0.35/0.40 m. Eğer Ö2'den sonra da gereken
salım sınırın üstünde kalıyorsa, sorun yazılım değil **geometri**:
ya araç daha alçalmalı ya ip uzamalı. Bu durumda faz, "doyuma ulaştım ve
yetmiyor" diye **açıkça durmalı**, 3 deneme boyunca aynı imkânsız işi
tekrarlamamalı.

### Ö4 — Arayüz sözleşmesini netleştir
`activate_pickup_mechanism(altitude_m=...)` — bu **nominal** mi **ölçülen**
mi? İki çağıran iki farklı şey anlıyor. Gerçek servo yazılmadan önce
netleşmeli (§4).

---

## 7 · Kapsam ve sınırlar

- 4 FAIL#3 koşumu (r1, r2b, r3b, r5b); r4b FAIL#1'de düştüğü için
  oturma verisi yok.
- Her koşumda 3 deneme × ~110 örnek = ~1330 örnek/koşum.
- `HOOK_PAYOUT_CHAIN_OFFSET_M`'in doğru değeri **ölçülmedi** — Ö2 açık.
- Ö1'in insertion'ı kapıya kadar götürüp götürmeyeceği **kanıtlanmadı**;
  §3'e göre tek başına yetmemesi bekleniyor.
- Kod ve config **değiştirilmedi**; tüm sayılar `HOOK_SEATING_RESULT`
  olayının `seat_trace` alanından ve mevcut kaynak koddan çıkarıldı.
