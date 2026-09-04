# GÖREV I — Çakışma kontrolü: Görev G bulgularının yeni geometriyle durumu

**Tarih:** 2026-09-04 · **Tip:** analiz · **Kod/config değişikliği: YOK**

Yeni spec: **kanca 25 cm · mıknatıs Ø35 mm · yaklaşma irtifası 30 cm.**
Aşağıda `docs/gorevG-*.md`'nin 10 dosyasındaki her ana bulgu, bu spec'e
karşı **geçerli / geçersiz / yeniden türetilmeli** diye ayrıldı.

---

## 1 · GEÇERLİ KALAN bulgular (geometriden bağımsız)

| # | bulgu | neden geometriden bağımsız |
|---|---|---|
| 1 | **EKF datum kayması** `ref_alt − home.alt = −0.177 m` | ULog'dan ölçüldü, kancayla ilgisi yok. **Genel sistem hatası.** Düzeltildi (`3c816f8f`), 1 mm uyumla doğrulandı. |
| 2 | **EKF ↔ gerçek kestirim hatası 0.09–0.29 m, değişken** | Kestirici doğruluğu. Yeni kanca bunu değiştirmez. Faz 1'in yeni tasarımında da **aynı belirsizlik** olacak. |
| 3 | **H1: `_reacquire_by_climbing` koşulsuz yukarı** | Mantık kusuru. Tavan **yükün** boyutundan ve dedektör kapısından türüyor — yük değişmiyor (0.14×0.05 m kutu). Düzeltildi. |
| 4 | **Tespit analizi** (HSV kapıları, 400 px² alan eşiği, kadraj tablosu) | Kamera + yük geometrisi. Kanca değişikliği bunlara dokunmuyor. |
| 5 | **Faz 1'in üç ayrı çıkışı** (FAIL#1/#2/#3) | Kod yolu yapısı. Yeni tasarımda çıkışlar yeniden kurulacak ama **sınıflandırma** geçerli. |
| 6 | **F serisinin Görev 3'e dokunmadığı** (F1 guard, rejoin, E4e) | Ayrı mekanizmalar, kanıtlı. |
| 7 | **Görev 2 isabet ölçümleri** (n=22 önce / n=8+ sonra) | Görev 3'ten bağımsız. |
| 8 | **`GOREV3_TRANSIT_SPEED_M_S` uygulanmıyor**; transport/finish hâlâ eski `goto_global_position_and_wait` yolunda | Faz 2/4, pickup geometrisinden bağımsız. |
| 9 | **`payload_cyl_red` ölü model**; `test_d2c` sentetik karesi eskimiş (5 m altıgen, daire yük, 3 m irtifa) | Test/asset hijyeni. |
| 10 | **Ö1'in kusur SINIFI**: aynı fonksiyona iki çağırandan iki farklı argüman | Çağrı sözleşmesi hatası. Yeni tasarımda da tekrarlanabilir — **ders geçerli**. |

---

## 2 · GEÇERSİZ olan bulgular (eski sabitlere dayalı)

| # | bulgu | neden geçersiz |
|---|---|---|
| A | **Ö2 `HOOK_PAYOUT_CHAIN_OFFSET_M` tartışması** (0.04236 vs 0.060) | İkisi de `D0 = 0.2007 m`'lik **mevcut zincirden** türedi. Kanca 25 cm olursa D0 değişir → **yeniden ölçülmeli.** |
| B | **Ö3 doyum korumasının SAYILARI** (gereken 0.390–0.488 m, sınır 0.350 m) | `HOOK_WINCH_MAX_EXTENSION_M = 0.35` ve eski zincir. **Sayılar geçersiz.** |
| C | **`GOREV3_DESCENT_ALTITUDE_M = 0.12` aday değeri** (%12 marj) | B'deki açıklardan türetildi. **Geçersiz** — üstelik yeni spec zaten 0.30 m diyor. |
| D | **"Faz 1 yapısal olarak imkânsız" hükmü (0/5)** | Eski vinç sınırına dayanıyordu. Yeni geometride **yeniden sorulmalı.** |
| E | **Oturma kapısı eşikleri** `SEAT_MAX_LATERAL_M = 10.25 mm` | `RECEIVER_MOUTH_RADIUS 23.25 − HOOK_NOSE_RADIUS 13.00`'ten türüyor, yani **pim-yuva** modelinden. Mıknatıs Ø35 mm ise bu model değişir. |
| F | **`HOOK_VISUAL_ALIGN_ALTITUDE_M = 0.90` gerekçesi** | 0.30 m'de kadrajın daralması + `HOOK_BODY_OFFSET_FORWARD_M = 0.175` üzerine kuruluydu. Yeni spec **30 cm'de ortalama** istiyor — bu, o gerekçeyle **doğrudan çelişiyor** (§4'te soru). |
| G | **`D0 = 0.20073 m` ölçümü** | Doğru ölçüm, ama **mevcut** SDF zincirinin. Yeni kanca ile taban çizgisi olur, hedef olmaz. |

**Ö3 korumasının KENDİSİ geçerli kalır:** ölçütü
`gereken = ulaşılan_salım + (−insertion)` ve **hiçbir sabit içermiyor**
(bunu `test_olcut_SABIT_ICERMEZ` koruyor). Yeni geometride
**karşılaştırdığı sınır** değişir, ölçüt değişmez.

---

## 3 · MEVCUT MODELİN GERÇEĞİ — spec ile üç çelişki

Kodu okudum; SITL modeli **CAD'den türetilmiş** ve yeni spec'le üç yerde
çelişiyor:

| kalem | **mevcut (CAD kaynaklı)** | **yeni spec** | fark |
|---|---|---|---|
| mıknatıs | `hook_magnet` **Ø10 × 2 mm**; yükün yuvası **Ø13.00** (`model.sdf:303-305`, kaynak `PCBV1_PARAMETERS.txt`) | **Ø35 mm** | **3.5×** |
| oturma modeli | **pim-yuva**: Ø26 burun, Ø46.5 yuva ağzı, 15.86 mm eksenel giriş (`hook_seating.py:80-99`) | mıknatıs teması | **farklı fizik** |
| kanca uzunluğu | base_link → burun **0.2007 m** (ölçüldü) | **0.25 m** | +50 mm |
| yaklaşma irtifası | 0.90 m'de hizala, 0.30 m'ye in | **0.30 m'de ortala** | §4 soru 2 |

Ek not: mıknatıs çekimi **simüle edilmiyor**; yakalama kuralı mesafeye
dayalı ve görev tarafında (`HOOK_MAGNET_CAPTURE_RADIUS_M`). Yani "mıknatıs
Ø35 mm" bir **yakalama yarıçapı** parametresine mi yoksa **fiziksel
geometriye** mi karşılık geliyor, bu ayrım B'nin tasarımını belirliyor.

---

## 4 · B'YE GİRMEDEN ÖNCE CEVAP GEREKTİREN SORULAR

> A, C ve D bu sorulardan bağımsız; onlara devam ediyorum.

**S1 — Donanım revizyonu mu, farklı bir şeyin tarifi mi?**
Mevcut ölçüler `PCBV1_PARAMETERS.txt` CAD dosyasından geliyor (o dosya bu
depoda yok, yalnızca referans veriliyor). "Mıknatıs Ø35 mm" **yeni bir CAD
revizyonu** mu (o zaman SDF + `hook_seating.py` sabitleri + CAD dosyası
birlikte güncellenmeli), yoksa mevcut Ø10 mıknatısın **etkili yakalama
alanı** mı (o zaman yalnızca `HOOK_MAGNET_CAPTURE_RADIUS_M` ayarlanır,
geometri durur)?

**S2 — "Kanca uzunluğu 25 cm" neyin uzunluğu?**
Üç aday: (a) base_link'ten kanca burnuna toplam mesafe (bugün 0.2007 m),
(b) vinç ipinin salım boyu (bugün en fazla 0.35 m), (c) kanca gövdesinin
kendi boyu. Hangisi?

**S3 — 30 cm'de ortalama, ölçülmüş bir engelle çelişiyor.**
`gorev3_pickup.py:57-70`'te kayıtlı ölçüm: 0.30 m'de kanca ofseti hedefi
kadrajın **501 px** aşağısına atıyor (yarı-kadraj 480 px) ve hedef
kadraj dışına çıkıyor; 0.30 m'de görev 30 yinelemede yalnızca 7 tespit
yapabilmiş. 0.90 m tam bu yüzden seçilmiş. Yeni tasarımda 30 cm'de
ortalama isteniyor — bu engeli nasıl aşacağız? Seçenekler: kanca ofsetini
küçültmek, kamerayı yeniden konumlandırmak, ya da "30 cm'de ortalama"yı
kanca ofseti uygulanmadan önce yapmak.

**S4 — Pim-yuva oturma kapısı kalacak mı?**
`hook_seating.py`'ın tamamı (lateral 10.25 mm, insertion −4…+22 mm, tilt
15°, dwell 0.30 s) pim-yuva içindir. Mıknatısa geçilirse bu kapı
**yeniden tanımlanmalı** (mıknatıs için "insertion" kavramı yok; temas +
mesafe var). Kapıyı mıknatıs modeline mi çevireceğiz, yoksa pim-yuva
fiziksel olarak duruyor ve mıknatıs yalnızca **tutma** mı sağlıyor?

**S5 — 60 s timeout, mevcut 12 s ile nasıl ilişkilenecek?**
Bugün `HOOK_CONTACT_TIMEOUT_S = 12.0` (deneme başına oturma penceresi) ve
`HOOK_PICKUP_ATTEMPTS = 3`. Yeni spec "bu tek deneme için 60 s" diyor.
60 s **oturma penceresinin** yerine mi geçiyor (12 → 60), yoksa
sarkıtma+yakalama+doğrulama dahil **tüm denemeyi** mi kapsıyor (yani
üstteki bir bütçe)?

---

## 5 · Bu turda ne yapılacağı

| madde | durum |
|---|---|
| **A** first-payload kimliği | ✅ bu sorulardan bağımsız — **başlıyorum** |
| **C** rota irtifaları | ✅ bağımsız |
| **D** rejoin teyidi | ✅ bağımsız |
| **B** Görev 3 yeniden tasarım | ⏸ **S1–S5 cevaplanmadan başlamıyorum** |
| **E** ADR'ler | en son |
