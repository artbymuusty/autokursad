# DEVİR 2 — Görev K / D: çekim ölçümü bitti, **yön değişti**

**Tarih:** 2026-09-05 · **33 commit, PUSH EDİLMEDİ** · Çalışma ağacı temiz
**Son commit:** `d9a2ee03`

Bu dosya `gorevK-D-probe-devir.md`'nin **yerine geçer**. Oradaki P1/P2/P3
planı **tamamlandı**; aşağıda sonuçları ve operatörün verdiği **yeni yön**
var.

---

## 1 · P1/P2/P3 KAPANDI

| | durum |
|---|---|
| **P1** probe kurulumu (yerleştirme 0.40 m, kapı 2.0 m) | ✅ |
| **P2** tilt anomalisi | ✅ **açıklandı** |
| **P3** A/B ölçümü | ✅ **alındı** |

### P3 sonucu: çekim yanal hatayı **kapatmıyor**

Kurulum ilk kez temizdi (yük **0.0°**, zincir sağlam, kapalı çevrim
ıraksamıyor) ve **çekim ilk kez tetiklendi** (11 adım, d 49.7 → 41.7 mm).

| | KONTROL | ÇEKİM |
|---|---|---|
| yanal medyan | **59.9 mm** | **60.3 mm** |
| yanal min | 44.5 mm | 41.4 mm |
| 17.5 mm altına inen | **0/246** | **0/247** |

Fark tek koşum gürültüsü mertebesinde.

**Sınır (açıkça):** tilt kapısı 493/493 ve 494/494 reddettiği için oturma
zaten imkânsızdı. Ölçülen şey çekimin **lateral** üzerindeki etkisiydi.
Kanca **serbest asılıyken** çekimin işe yarayıp yaramayacağı **sınanmadı**;
çekim ayarı (kazanç 0.6, adım tavanı 20 mm, periyot 0.4 s) **hiç taranmadı**.

---

## 2 · BELİRLEYİCİ BULGU — erişim irtifadan BAĞIMSIZ

P2'nin ham ölçümü:

```
kanca dikeyden = 153.2°      yuva dikeyden = 0.0°   (yük DİK)
vinç  achieved = 0.3203      span = 0.0941  (gergin: 0.235)
      fold = [20.4, 68.2, 68.6, 48.2]        ← zincir BÜKÜLMÜŞ
      nose_z = -0.0987                        ← burun ZEMİNİN 10 cm ALTINDA
```

0.30 m irtifada 0.32 m salım + 0.25 m kanca ⇒ burun zemine sürülüyor,
zincir bükülüyor, kanca yan yatıyor ve **tilt kapısı kapanıyor**.

**Aritmetik:** komut edilen irtifa 0.30 m iken burun −0.099 m'de →
base_link'ten burna toplam erişim ≈ **0.40 m**, ve bu **salımla birlikte
sabit**, irtifadan bağımsız. *(Bu koşumda gerçek irtifa ayrıca ölçülmedi;
sayı komut edilen irtifaya dayanıyor.)*

### Bunun sonucu: **sabit irtifa aramak yanlış yaklaşım**

`GOREV3_APPROACH_ALTITUDE_M` için "doğru sayıyı" aramak — 0.30, 0.45,
0.12 — bu oturumda defalarca denendi ve her seferinde başka bir yerde
tıkandı. Erişim sabit, irtifa hatası (Ö5: EKF↔gerçek **0.09–0.29 m**,
değişken) ise sabit değil. **Sabit bir sayı, değişken bir hatayı
karşılayamaz.**

---

## 3 · YENİ YÖN — **adaptif alçalma** (operatör kararı)

Sabit hedef irtifa yerine, sistem **kilitlenme sağlanana kadar kademeli
alçalsın**. Akış:

1. İlk bırakılan yükün **kayıtlı konumuna** git
2. **Şekli** görüntü işlemeyle odakla/ortala *(büyük ölçek)*
3. **Yükü** görüntü işlemeyle odakla/ortala *(küçük ölçek, hassas)*
4. Yüke **kilitlen** — hedef sabitlensin, referans kayması olmasın
5. **Tekrar ortala** — kilitlenmeden sonra son hassas düzeltme
6. **Alçalmaya başla** — sabit bir hedefte durmak yerine, oturma
   kapılarının **hepsi** sağlanana kadar **kademeli** alçal:
   **17.5 mm lateral · 5 mm eksenel · 8° tilt · 0.60 s dwell**.
   Hangi mesafeden yakalanacağını (0.30 / 0.35 / 0.40 … her ne ise)
   **sistem kendi ölçümüyle bulsun**, sabit sayı verilmesin.
7. **Güvenlik alt sınırı:** burun zemine değmeden/gömülmeden **önce**
   duracak bir `nose_z` güvenlik payı olmalı — sonsuz alçalma ve zemin
   teması riski yok.

### Bu değişiklik neyi DEĞİŞTİRMİYOR

- **S4 oturma kapıları aynen kalıyor** (17.5 / 5 / 8° / 0.60 s)
- **Manyetik çekim modeli aynen kalıyor** (5 cm menzil, kazanç/adım/periyot)
- Değişen tek şey: **"hangi irtifada dur" kararı** sabit sayıdan
  **gerçek zamanlı geri beslemeye** taşınıyor (kapılar geçildi mi, burun
  güvenli mesafede mi).

---

## 4 · SIRADAKİ İŞ

> **`GOREV3_APPROACH_ALTITUDE_M`'i sabit hedef olmaktan çıkarıp,
> kademeli-alçal-kapılar-geçilene-kadar mantığına çevirmek — yeni bir
> state/alt-döngü olabilir, `motion_fsm`'in çekirdeğine dokunmadan
> pickup fazının kendi içinde inşa edilmeli.**

Kısıtlar:
- `motion_fsm.py`'ın çekirdek state tanımları (CLIMB/HOLD/CRUISE/DESCEND/
  ARRIVAL_HOLD) **dokunulmaz**
- Görev C, A, D, J **dokunulmaz**
- Yeni mantık `gorev3_pickup.py` içinde, mevcut dış 3-deneme döngüsünün
  (`GOREV3_PICKUP_MAX_ATTEMPTS`, 60 s bütçe) **içinde** yaşamalı
- Güvenlik payı **ölçümden türetilmeli**, seçilmemeli

Açık kalanlar (yeni yön bunları kapatmıyor, sadece erteliyor):
- Kanca serbest asılıyken çekim işe yarıyor mu — **sınanmadı**
- Çekim ayarı taraması — **yapılmadı**
- Görev K'nın **E-F-G-H** maddeleri — **operatör kararı bekliyor**

---

## 5 · OKUNACAK DOSYALAR (öncelik sırasıyla)

1. **bu dosya**
2. `docs/gorevK-P3-ab-sonuc.md` — A/B sayıları + P2'nin ham ölçümü
3. `docs/gorevK-S1-probe-v2.md` — K1/K2/K3, probe'un kendi kusurları
4. `tools/magnet_attract_probe.py` — araç; P1/P2 notları kod içinde
5. `docs/gorevG-O5-kok-neden.md` — **EKF↔gerçek 0.09–0.29 m**; adaptif
   alçalmanın neden gerekli olduğunun sayısal temeli
6. `docs/gorevI-OA-sonuc-OB-butce.md` — 60 s bütçesinin gerçek dağılımı
   (ön hazırlık 53.5–58.6 s; adaptif alçalma bu bütçeye sığmalı)

---

## 6 · ÇALIŞMA DURUMU

- **33 commit, push edilmedi**
- Çalışma ağacı temiz (tek `M`: `default.sdf`, SITL her açılışta üretir)
- Süreç kalıntısı yok
- Test paketi son tam koşumda **568 geçti / 1 atlandı / 0 başarısız**

### Operasyonel tuzaklar (bedeli bu turda ödendi)
- Probe'u **`gz_env.sh` source etmeden** çalıştırma → poz izleyici sessizce boş döner
- Koşumlar arası `mavsdk_server` öldürülmeli, **UDP 14540** boşalana kadar beklenmeli
- Bu kabukta foreground `timeout` **yok**; uzun koşumlar arka planda
- gRPC **"Stream removed"** iki koşumu düşürdü (altyapı oynaklığı, probe değil) — temiz yeniden başlatma çözdü
