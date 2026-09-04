# GÖREV G / Ö5 — tutma irtifası ölçümü + doyum korumasının bağımsızlığı

**Tarih:** 2026-09-04 · **Tip:** ölçüm + değerlendirme · **Kod/config değişikliği: YOK**
**Veri:** o1a / o1b / o1d — Ö1 sonrası 3 bağımsız koşum (her birinde tam SITL yeniden başlatma)

---

## 0 · ÖNCE BİR DÜZELTME

Bir önceki raporda (`gorevG-O1-O2-sonuc.md` §4) *"araç 0.30 m komut edilirken
0.36–0.47 m'de kalıyor"* demiştim. **Bu yanlıştı.** O sayı ölçüm değil,
kancanın dünya pozundan **gergin zincir** ve **B = 0.240** varsayımıyla
yapılmış bir **geri hesaptı.**

Doğrudan telemetri ölçümü tam tersini söylüyor: araç komutun **ÜSTÜNDE
değil, ALTINDA.** Aşağıdaki §1 ölçümdür; önceki §4 türetmeydi ve
**geçersizdir.**

---

## 1 · Ö5 ÖLÇÜMÜ — araç nerede duruyor

`VEHICLE_TELEMETRY.position[2]` (relative altitude), **alma penceresi
boyunca**, `pickup_attempt_start` → `HOOK_SEATING_RESULT` arası:

| koşum | komut | p10 | **p50** | p90 | n | **hata** |
|---|---|---|---|---|---|---|
| o1a | 0.300 | 0.090 | **0.115** | 0.145 | 154 | **−0.185 m** |
| o1b | 0.300 | 0.088 | **0.096** | 0.098 | 143 | **−0.204 m** |
| o1d | 0.300 | 0.117 | **0.124** | 0.126 | 145 | **−0.176 m** |

**Üç koşumda da araç, komut edilen 0.30 m'nin ~0.19 m ALTINDA duruyor.**

Ve **çok sıkı duruyor**: o1b'de p10–p90 aralığı yalnızca **10 mm**,
o1d'de **9 mm**. Yani bu bir salınım ya da yakınsayamama değil —
**kararlı bir sapma.** Kontrolcü bir yere oturuyor, ama komut edilen
yere değil.

`_pick_alt` (0.093–0.125) bu dağılımın **içinde** — yani `_pick_alt`
"geçici bir alçalma dibi" değilmiş; pencereyi doğru temsil ediyormuş.
Ö1'in gerekçesindeki bu ikinci cümle de **düzeltilmelidir**; ama Ö1'in
kendisi (geri çekme engellensin) ölçümle ayakta: salım 0.19 → 0.33 m
olunca insertion −205 mm'den ~0'a geldi.

## 1.1 Kök neden — BELİRLENMEDİ

Ölçüm "nerede durduğunu" verdi, "neden" vermedi. Adaylar, hiçbiri
kanıtlanmadı:

- **Yer etkisi / PX4 konum kontrolcüsü**: 0.30 m, x500 için rotor
  çapının altında bir irtifa; itki modeli bu bantta kalibre değil.
- **Kanca + ip zeminde yük aktarıyor**: 0.33 m salımla, araç 0.10 m'deyken
  zincir yere değmek zorunda (base_link'ten burna gergin mesafe
  D0+e = 0.53 m). Zemine yaslanan kanca aracı aşağı çekiyor olabilir.
- **Datum kayması**: `-GOREV3_DESCENT_ALTITUDE_M` NED-down olarak EKF
  orijinine, `relative_altitude_m` ise home'a göre. İkisi 0.19 m
  kaymışsa araç "0.30'dayım" sanırken 0.11'de olur.

**Ayırt edici ölçüm (bir sonraki tur):** aynı pencerede
`vehicle_local_position.z` (ULog) + `hook_body_link` dünya pozu +
`relative_altitude_m` üçünü yan yana koymak. Bu üçlü, hangi katmanın
kaydığını tek koşumda söyler.

---

## 2 · Geometri modeli veriyi ÜRETMİYOR — Ö2 bu veriyle kapanamaz

Basit gergin-zincir modeli (`nose = base − D0 − e`, `base = alt + B`)
ile ölçülen insertion'dan `B` geri hesaplanınca **sabit çıkmıyor**:

| koşum | alt (p50) | e | insertion | geri hesaplanan `B` |
|---|---|---|---|---|
| o1a/1 | 0.115 | 0.3285 | +4.6 mm | **0.484** |
| o1b/1 | 0.096 | 0.3287 | −94.9 mm | **0.599** |
| o1d/1 | 0.124 | 0.3285 | −114.1 mm | **0.589** |

`B` bir **sabit** olmak zorunda (araç yerdeyken base_link'in dünya Z'si);
0.48–0.60 arası değişmesi modelin bu rejimde **geçerli olmadığını**
söylüyor. Beklenen de bu: 0.10 m irtifada 0.33 m salım, zincirin
yere değmesi ve **ipin gevşemesi** demek — gergin-zincir varsayımı düşer.

**Sonuç:** `HOOK_PAYOUT_CHAIN_OFFSET_M` bu koşumların verisinden
türetilemez. Ö2 açık kalıyor ve **sabit değiştirilmedi.** (Kaydedilen
iki aday, 0.04236 ve 0.060, ölçülen gereksinimin — §3'te ~0.24 m
mertebesi — çok altında; yani formül **her irtifada eksik salım**
hesaplıyor olabilir. Bu da kanıtlanmadı, çünkü model geçerli değil.)

---

## 3 · DOYUM KORUMASI — Ö5'e BAĞLI DEĞİL, hemen uygulanabilir

**Sorunun cevabı: EVET, bağımsız olarak eklenebilir.** Şartı, formülü
değil ÖLÇÜMÜ kullanmak.

### 3.1 Neden mevcut doyum kontrolü işe yaramıyor

`extend_winch_for` zaten `wanted > HOOK_WINCH_MAX_EXTENSION_M` diye
bakıyor ve `[HOOK] VINC DOYUMU` logluyor (`gz_payload_actuator.py:1447`).
Ama `wanted` **formülden** geliyor — ve formül 0.330 m üretiyor, sınır
0.35 m. **Doyum hiç tetiklenmiyor**, oysa gerçekte gereken salım
0.42–0.45 m. Yani mevcut kontrol, tam da yanlış olduğu bilinen sabite
dayandığı için kör.

### 3.2 Ölçüme dayalı ölçüt — sabit içermiyor

```
gereken_salim = ulasilan_salim + (−insertion)
```

İkisi de **doğrudan ölçülüyor**: `winch_state().achieved_m` ve
`SeatingGeometry.insertion_m`. Formül yok, `CHAIN_OFFSET` yok, `B` yok,
irtifa yok. Dolayısıyla **Ö5'in kök nedeninden ve Ö2'den bağımsız.**

### 3.3 Mevcut veride ayırt ediciliği — 9 denemenin 9'unda doğru

| deneme | ulaşılan | insertion | gereken | karar | gerçekleşen |
|---|---|---|---|---|---|
| **o1a/1** | 0.3285 | **+4.6 mm** | **0.3239** | **sığar → devam** | kapıya girdi ✅ |
| o1a/2 | 0.3285 | −95.3 | 0.4238 | DOYUM → dur | boşa gitti |
| o1a/3 | 0.3284 | −103.8 | 0.4322 | DOYUM → dur | boşa gitti |
| o1b/1 | 0.3287 | −94.9 | 0.4236 | DOYUM → dur | boşa gitti |
| o1b/2 | 0.3286 | −124.2 | 0.4528 | DOYUM → dur | boşa gitti |
| o1b/3 | 0.3285 | −106.4 | 0.4349 | DOYUM → dur | boşa gitti |
| o1d/1 | 0.3285 | −114.1 | 0.4426 | DOYUM → dur | boşa gitti |
| o1d/2 | 0.3285 | −115.4 | 0.4439 | DOYUM → dur | boşa gitti |
| o1d/3 | 0.3284 | −114.0 | 0.4424 | DOYUM → dur | boşa gitti |

**Tek "devam" kararı, kapıya giren tek denemeye denk geliyor.**
Yanlış pozitif yok, yanlış negatif yok.

o1b ve o1d'de gereken salım **her denemede** 0.35 m sınırının üstünde:
o koşumlarda alma **yapısal olarak imkânsızdı** ve sistem 3 denemeyi,
her biri ~12 s + yeniden hizalama, sessizce yaktı.

### 3.4 Riski neden düşük

- **Salt gözlem üzerine kurulu**: hiçbir kontrol değeri, eşik ya da
  zamanlama değişmiyor; yalnızca *"devam etme"* kararı ekleniyor.
- **Yalnızca ilk deneme SONRASI karar verir** — ilk deneme her zaman
  yapılır, yani hâlihazırda çalışan hiçbir senaryo kaybedilmez
  (o1a/1 aynen çalışırdı).
- **Ölçüm yoksa koruma da yok**: `insertion` veya `achieved_m`
  okunamazsa eski davranış (aynı desen `extend_winch_for`'daki geri
  çekme korumasında da kullanıldı).
- **Kazanç ölçülü**: koşum başına ~2 boşa deneme × (12 s pencere +
  yeniden hizalama) — 600 s'lik görev bütçesinde 30–50 s.

### 3.5 Ne YAPMAZ

Bu koruma **hiçbir almayı başarılı kılmaz.** Yalnızca imkânsız olanı
erken ve **açıkça** bitirir; `HOOK_SEATING_RESULT`'a "yapısal erişim
dışı" gerekçesi düşer ve arıza, "3 kez denedi tutmadı" belirsizliğinden
çıkıp ölçülmüş bir sayıya bağlanır.

---

## 4 · Sıralama önerisi

| # | iş | Ö5'e bağlı mı | risk |
|---|---|---|---|
| **1** | **§3'teki doyum koruması** | **HAYIR** | **düşük** — salt gözlem, ilk deneme korunur |
| 2 | Ö5 kök nedeni (§1.1 ayırt edici ölçümü) | — | ölçüm |
| 3 | Ö2 / `CHAIN_OFFSET` | evet — model ancak Ö5 çözülünce geçerli olur | orta |
| 4 | Ö4 arayüz sözleşmesi | evet | düşük |

**Ö5'in kök nedeni beklenmeden §3 uygulanabilir.** Uygulanmadı — onay
bekliyorum.

---

## 5 · Kapsam ve dürüstlük

- Ö5 **ölçüldü** (nerede duruyor), **kök neden belirlenmedi** (neden).
- Bir önceki raporun §4'ü (türetilmiş 0.36–0.47 m) **geçersiz**; §0'da
  açıkça düzeltildi.
- Ö1'in gerekçesindeki *"`_pick_alt` pencereyi temsil etmiyor"* cümlesi
  de **yanlışmış** — `_pick_alt` dağılımın içinde. Ö1'in kendisi
  (geri çekme engelleme) ölçümle ayakta duruyor, gerekçesinin o cümlesi
  değil.
- §3'ün ayırt ediciliği **9 denemede** gösterildi; hepsi Ö1 sonrası,
  aynı 3 koşumdan. Bağımsız yeni koşumla doğrulanmadı.
- Kod ve config değiştirilmedi.
