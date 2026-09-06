# DEVİR — KURSAD40 v34, Görev K→S zinciri sonrası

**Tarih:** 2026-09-06 · **62 commit, PUSH EDİLMEDİ** · **659 test geçiyor, 1 atlandı**
Çalışma ağacı temiz (tek `M`: `Tools/simulation/gz/worlds/default.sdf`, SITL her açılışta üretir)

---

## 0 · SIRADAKİ İŞ (yeni oturum buradan başlasın)

> **GÖREV P/C — dashboard'lu izleme turu. HENÜZ YAPILMADI.**
>
> Operatör, gerçekleşen uçtan uca başarılarda kilidin **gerçekten SERVO3
> kavramasıyla** oluştuğunu **görsel olarak** teyit etmek istiyor: mission
> dashboard'u açıp Görev N'de eklenen **SERVO DURUM panelinden** SERVO1/2/3'ü
> canlı izleyecek ve `grip_engaged` → `pickup_verified` iki bayraklı
> doğrulamanın akışta göründüğünü görecek.
>
> **Çalıştırılacak tek komut** (dashboard varsayılan açık):
> ```
> .scripts/olds/v34/demo/run_demo_gz.sh
> ```
> Koşum sırasında ajan paralelde event log'u takip edip özet çıkarmalı:
> GATE olayları, `MAGNET_LOCKED`, `SERVO3_GRIP_ENGAGED` zamanlaması,
> `pickup_verified` sonucu, uçtan uca başarı/başarısızlık.
>
> ⚠️ **Koşumdan önce YÜK KAPISI:** yük yüksekken (iOS Simulator / Spotify
> vb.) alınan sonuçlar geçersiz — "telemetri bayat / detector hata veriyor"
> ile düşüyor. Eşik: 1 dk yük ≤ 10. Bugün 4 koşum bu yüzden atıldı.

---

## 1 · ZİNCİRİN ÖZETİ — hangi görev neyi çözdü

| görev | sorun | çözüm | kanıt |
|---|---|---|---|
| **K** | Sabit `GOREV3_APPROACH_ALTITUDE_M` isabet etmeliydi ama pencere yalnızca **70 mm**; EKF hatası 90–290 mm | **Adaptif alçalma** — irtifayı komut etme, `insertion_m`'i kapat | C1 +61…+152 mm (üstte), P3 +46 mm (altta): aynı sabit, iki zıt arıza |
| **M** | Mıknatıs "çekim" **taklitti** — aracı oynatıyordu, kanca güvertede durduğu için hiçbir şey olmuyordu | **Gerçek Gazebo kuvvet eklentisi** (`MagnetForceSystem`), Newton 3 ile yüke tepki | Taklit: 7 adımda 33.8→33.4 mm. Gerçek: 29.2→15.0 mm / 0.75 s |
| **M/2** | Oryantasyon düzeltmesi **hiç yoktu** (`AddWorldForce` kütle merkezine = sıfır tork) | Dipol hizalama torku `τ = k(â×â) − c·ω` | Devrilmiş kancayı 22.8°→0.2°, 0.25 s |
| **N** | Servo3 kilit sonrası gecikme **yoktu**; servo açıları belgesizdi; dashboard'da servo görünürlüğü yoktu | 2.0 s doğrulama penceresi (kapılar örneklenerek), açılar config'e, **SERVO DURUM paneli** | — |
| **O** | Settle noktasındaki yanal 1.9–217 mm, **kontrolsüz** | İniş başlangıç irtifası **ölçülüyor**; şakul yerine "durdu mu" + minimum bekleme | 18 denemede istisnasız korelasyon |
| **P** | Doğrulanamayan durumda "**alındı**" varsayılıyordu (`lifted_m is None` → `True`) | `grip_engaged` ≠ `pickup_verified`; **kanıt yokluğu = başarısızlık** | Gerçek donanımda servo3 geri bildirimi **YOK** — tek kanal görüntü işleme |
| **Q** | Sıçramanın kök nedeni | **ADIM 5, kanca ofsetini İKİNCİ KEZ uyguluyor** — ADIM 4b zaten kanca-referanslı | `visual_alignment.py:64` = `recv − hook`; ölçüm: `\|araç−yuva\|−\|kanca−yuva\| = 85–91 mm` = `hook_mount` x |
| **R** | Q'nun düzeltmesi | Ofset kaldırıldı, **irtifa işi korundu** | Sıçrama ortanca +201.9 → +36.1 mm |
| **S** | Görsel blok 26.7 s, 8.5 s'i kör iterasyon | Yaklaşma irtifası **görüş eşiğinden türetiliyor** (0.30 → 0.58) | "hedef kayboldu" 51 → 0–2 satır |

---

## 2 · ÇÜRÜYEN HİPOTEZLER — tekrar denenmesin

| hipotez | nasıl çürüdü | maliyet |
|---|---|---|
| **"Kanca askı noktasının altında şakulde olmalı"** (Görev O bekleme ölçütü) | **TERSTİ.** ADIM 5 aracı kasıtlı 175 mm ötelıyor; şakul = yuvadan 175 mm uzak. 11 örnekte **tam anti-korelasyon**, toplam her satırda ~175 mm | 5 koşum, **0/15 kilit** |
| **"Hız eşiğini düşürmek yardım eder"** | Veri karşı çıktı: en **düşük** hızla çıkan deneme (0.007 m/s) en kötü sonucu (44.9 mm), en yükseği (0.043) iyi sonucu verdi | uygulanmadı |
| **"Araç hâlâ iniyor, o yüzden hedefi göremiyor"** | `[KANCA_IZ] alt=0.238–0.265` — araç **zaten varmıştı**, hatta komutun altına inmişti. Sebep dedektörün 0.50 m görüş eşiği | uygulanmadı (ölçümle önce yakalandı) |
| **Ö-B'nin "B1 ~15 s kazandırır" tahmini** | O tahmin `HOOK_ALIGN_MAX_CORRECTIONS 6→3` + reacquire kısıtı üzerineydi; **ikisi de zaten uygulanmıştı** (`bf68e3ed`). Gerçek kazanç ~5.7 s | — |
| **B2 ("settle'ı pencereye al") faydalı** | `_settle_hook_onto` artık **15 denemenin yalnızca 5'inde** koşuyor; 10'unda taşınacak maliyet yok. Ayrıca 0.90 m'de kapı geçemez → örtüşme **fiziksel olarak imkânsız** | uygulanmadı |

---

## 3 · GÖREV S SONUCU (6 koşum / 13 deneme)

```
kilit:        4/6 kosum (%67)      <- referans 2/3 (%67) YAKALANDI, daha buyuk orneklemde
uctan uca:    4/6 kosum (%67)
gorsel blok:  26.7 s -> ~21 s      (16.6 / 25.7 / 25.1 / 17.5 s)
butce marji:  0.3 / 1.1 / 8.0 / 12.4 s   (referans 2.9 s -- ortalama artti, DAGILIM GENIS)
aligner:      4.7 - 26.0 mm        (onceki 6.5-29.7; DOGRULUK KORUNDU)
sicrama:      -11.0 ... +44.3 mm, ortanca +27.4   (Q oncesi +201.9)
```

**Sıçrama artık negatif de olabiliyor** (−11.0, −0.9 mm) — 175 mm'lik sistematik terimin gerçekten gittiğinin kanıtı.

---

## 4 · AÇIK KALANLAR

1. **Görev P/C — dashboard'lu izleme** (§0). Operatörün öncelikli isteği.
2. **Değişkenlik:** iyi denemeler `inis_lat` 3.0 mm, kötüler 105.6 mm.
   `yanal_menzil_disi` ve `devrilmis_kanca` hâlâ deneme kaybettiriyor.
   13 denemenin 9'u bütçeden kesildi.
3. **Bütçe marjı dağılımı:** iki başarı 0.3 s ve 1.1 s ile **tam sınırda**.
4. **In-çık-in çevrimi (~14 s):** araç 0.90→0.58 iniyor, ADIM 5 0.90'a
   çıkıyor, adaptif iniş yine ~0.35'e iniyor. **Uygulanmadı** — görsel işin
   hangi irtifada yapıldığını değiştirir, doğruluk şartına dokunur.
5. **Ortalama 0.58 m'de yakınsamıyor:** `dy` ±150 px salınıyor, 111
   iterasyon (12.8 s). Kör iterasyonların yerini **salınan** iterasyonlar aldı.
6. **PUSH KARARI** — 62 commit bekliyor.
7. Görev C (2way 10 m rota irtifası), Görev K'nın E-F-G-H maddeleri,
   `docs/TODO-adr-guncellemeleri.md` (7 madde), `docs/TODO-CAD-guncelleme.md`,
   `docs/TODO-guvenlik-inis-oncesi-vinc.md`.

---

## 5 · OKUNACAK DOSYALAR (öncelik sırasıyla)

1. **bu dosya**
2. `docs/gorevQ-sicrama-kok-neden.md` — kök neden, tam kanıt
3. `docs/gorevP-dogrulama-kanallari.md` — hangi doğrulama kanalı nerede var;
   **gerçek donanımda servo3 geri bildirimi YOK**
4. `docs/gorevO-gorsel-hizalama-darbogaz-analiz.md`
5. `docs/gorevM-oryantasyon-analiz.md`, `docs/gorevK-adaptif-alcalma-faz1.md`
6. `core/mission/gorev3_pickup.py` — her sabitin türetmesi kendi yorumunda

## 6 · OPERASYONEL TUZAKLAR

- **Yük kapısı** (§0) — bugün 4 koşum yükten kayboldu
- `gz_env.sh` source edilmeden probe çalıştırma → poz izleyici sessizce boş
- Koşumlar arası `mavsdk_server` öldürülmeli, UDP 14540 boşalmalı
- Bu kabukta foreground `timeout` yok; zsh **değişkeni sözcüklere ayırmaz**
  (dosya listeleri için dizi kullan)
- `ls -t` aliaslı (eza) — `/bin/ls -t` kullan
