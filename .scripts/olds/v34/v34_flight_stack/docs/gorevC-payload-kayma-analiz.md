# Görev C — Payload Bırakma Sırasında Yanal Kayma (FAZ 1: Analiz)

**Tarih:** 2026-09-03 · **Kod değişikliği YOK.**
**Veri:** iki tam Görev 2 koşumu, **4 bırakma** — PX4 ULog + görev olay kayıtları.

---

## 0. Sonuç

| Hipotez | Karar | Dayanak |
|---|---|---|
| **3. PX4 mod değişikliği** | **ÇÜRÜTÜLDÜ** | Dört bırakmanın ±2 s penceresinde de `nav_state` **sabit 14 (OFFBOARD)**. Hiç geçiş yok. |
| **2. Setpoint akış boşluğu** | **KISMEN** | Aktüatör çağrısı **1.13–1.31 s** boyunca yeni setpoint göndermiyor (n=4, tutarlı). **Ama Offboard kaybedilmiyor** — MAVSDK son setpoint'i tekrarlıyor. `nudge_forward` de bitişte sıfır hız gönderiyor. |
| **1. Fiziksel (kütle/CG)** | **TETİKLEYİCİ DEĞİL** | Aynı payload kütlesi ve aynı ayrılma fiziğiyle sapma **0.052 – 2.225 m** arasında **43 kat** değişiyor. Ayrılma olayı bunu açıklayamaz. |

**Ölçülen korelasyon:** sapma, ayrılma olayıyla değil **bırakmaya girerken taşınan artık yanal hızla** ilişkili.

---

## 1. Aktüatör penceresi (ULog hizalaması gerektirmez)

`MOUNT_VECTOR_MEASURED` → `PAYLOAD_RELEASE_CONFIRMED` arası, yani servo çağrısının bloklama süresi:

| Koşum | Payload 1 | Payload 2 |
|---|---|---|
| `af23a346ffc1` | 1.307 s | 1.129 s |
| `90d638b5d3e7` | 1.164 s | 1.193 s |

Bu pencerede görev kodu **hiç yeni setpoint göndermiyor** (`payload_release.py:234-247`:
`servo_at` → aktüatör → `detach_latency`). PX4 ~500 ms setpoint'siz kalınca Offboard'dan
düşer; **düşmedi** (bkz. §2), çünkü MAVSDK Offboard eklentisi son setpoint'i kendi
tekrarlıyor. `nudge_forward` da bitişte `_send_setpoint(0,0,0)` yapıyor
(`centering_controller.py`), yani "unutulmuş ileri hız komutu" değil.

> Not: sıfır **hız** setpoint'i hızı söndürür ama **konumu geri getirmez** — pozisyon
> geri beslemesi yoktur. Pencereye hızla girilirse, o hız boyunca alınan yol kalıcıdır.

---

## 2. Bırakma anı ±2 s — ham ölçüm

Hizalama çapası: `İniş yapılıyor` (görev logu) ↔ `AUTO_LAND` (ULog `nav_state`).

### Koşum `90d638b5d3e7` (çapa doğrulandı)

| | Payload 1 | Payload 2 |
|---|---|---|
| `nav_state` (±2 s) | **[14] OFFBOARD** | **[14] OFFBOARD** |
| \|v_xy\| **önce** (−2..0 s) | **0.131 m/s** | **0.518 m/s** |
| \|v_xy\| sonra (0..+2 s) | 0.139 m/s | 0.497 m/s |
| vz sonra | −0.008 … −0.002 | −0.085 … +0.019 |
| **yanal sapma +2 s** | **0.163 m** | **2.225 m** |
| roll p95 / max | 1.26° / 1.35° | 3.26° / 3.43° |
| pitch p95 / max | 1.42° / 3.18° | 4.42° / 4.43° |

Payload 2'nin zaman serisi (bırakma konumundan sapma):

```
  -1.00s  0.230 m   |v_xy|=0.485     <- AYRILMADAN ONCE zaten hareket halinde
  -0.50s  0.142 m   |v_xy|=0.513
  +0.00s  0.000 m   |v_xy|=0.459     <- bırakma
  +0.50s  0.264 m   |v_xy|=0.290
  +1.00s  0.681 m   |v_xy|=0.245
  +2.00s  2.241 m   |v_xy|=0.499
```

### Koşum `af23a346ffc1` (çapa daha zayıf — aşağıdaki uyarıya bakınız)

| | Payload 1 | Payload 2 |
|---|---|---|
| `nav_state` | [14] OFFBOARD | [14] OFFBOARD |
| \|v_xy\| önce | 0.091 m/s | 0.139 m/s |
| **yanal sapma +2 s** | **0.052 m** | **0.148 m** |
| roll / pitch p95 | 1.33° / 0.75° | 2.60° / 3.11° |

> **Ölçüm uyarısı:** bu koşumun çapasında payload 1 anında ULog irtifası 3.29 m
> çıkıyor, oysa rapor edilen bırakma irtifası 0.48 m. Yani bu koşumun zaman
> hizalaması **birkaç saniye kaymış olabilir**; değerleri destekleyici kabul
> ettim, belirleyici değil. Koşum `90d638b5d3e7`'nin çapası her iki bırakmada da
> irtifa bakımından tutarlı.

---

## 3. Hipotezlerin değerlendirmesi

**Hipotez 1 (fiziksel) — tetikleyici değil.** Dört bırakmanın payload kütlesi
(simülasyonda 0.15 kg), ayrılma mekanizması ve irtifası aynı. Sapma yine de
0.052 / 0.148 / 0.163 / **2.225** m. Ayrılma fiziği tetikleyici olsaydı dördü
benzer olurdu. Ayrıca büyük sapmalı olayda araç **ayrılmadan 1 s önce** zaten
0.485 m/s ile hareket ediyordu.

**Hipotez 2 (yazılımsal) — mekanizma var, ama "Offboard kaybı" değil.**
1.13–1.31 s'lik pencere gerçek ve ölçülü. Ancak `nav_state` sabit kaldı; MAVSDK
son setpoint'i tekrarladığı için mod düşmedi. Kalan mekanizma: bu pencerede
**pozisyon kilidi yok** — yalnızca sıfır hız komutu var, o da konumu geri
getirmiyor. Pencereye 0.5 m/s ile girilirse ~0.6 m yol o pencerede alınır.

**Hipotez 3 (mod değişikliği) — çürütüldü.** Dört pencerede de tek `nav_state`
değeri: 14. Koşumdaki tek mod geçişleri kasıtlı mission-resume'lar
(t=125.6 s, bırakmadan ~12 s sonra) ve sondaki `AUTO_LAND`.

---

## 4. Kanıtlanan kök neden

> **Kayma, payload'ın ayrılmasından doğmuyor.** Ölçülen büyüklüğü belirleyen şey,
> aracın bırakma dizisine **girerken taşıdığı artık yanal hız**. Bırakma dizisi
> (irtifa okuma → mount vektörü → servo → ayrılma onayı) boyunca **1.13–1.31 s**
> aktif bir **pozisyon kilidi yok**; yalnızca sıfır-hız setpoint'i var ve o
> konumu geri getirmiyor. Artık hız düşükse (0.09–0.14 m/s) sapma 0.05–0.16 m'de
> kalıyor; yüksekse (0.52 m/s) 2.2 m'ye çıkıyor.

**Açık kalan:** artık hızın neden koşumdan koşuma 0.09–0.52 m/s arasında
değiştiği ölçülmedi (yaklaşma/alçalma fazının çıkışıyla ilgili olabilir).
n=4 ile korelasyon güçlü ama nedensellik için daha fazla koşum gerekir.

**Eşik veya düzeltme önermiyorum** — FAZ 2 kararı sizin.

---

## 5. FAZ 2 için not (uygulanmadı)

Ölçüm, sizin listenizdeki **"yazılımsal"** koluna işaret ediyor ama önerdiğiniz
biçimden farklı: kapatılacak şey bir *akış boşluğu* değil, bırakma penceresinde
**pozisyon kilidinin olmaması**. `go_to_and_center()` ve Climb-then-Cruise'a
dokunulmasına gerek yok; müdahale `payload_release.py`'nin servo penceresiyle
sınırlı kalabilir.
