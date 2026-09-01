# V33 Spesifikasyon Sapmaları — Tarihli Düzeltme Kaydı

**Oluşturulma:** 2026-08-24
**Kapsam:** `Flowchart_40.pdf` ve `KURSAD40_v33_Gorev_Sistemi.pdf`

## Bu dosya neden var

V33 spesifikasyon belgeleri **bu repoda bulunmuyor** (PDF olarak dışarıda
tutuluyor). ADR-012'de yaptığımız gibi yanlış cümlenin üstüne yerinde
tarihli bir düzeltme notu düşmek bu yüzden mümkün değil. Bunun yerine
sapmalar burada, aynı disiplinle kayıt altına alınır:

- **spec ne diyor**, **kod ne yapıyor**, **hangisi doğru ve NEDEN** (ölçüm
  veya belgelenmiş operatör kararı referansıyla).

Bir sapmanın burada olması "kod yanlış" demek DEĞİLDİR. Aşağıdaki iki
maddede **spec bayattır, kod doğrudur** ve gerekçesi ölçümle kayıtlıdır.

---

## SAPMA-01 — Bırakma irtifası: spec 0.30 m, kod 0.45 m

**Spec md.8 / md.10 (Görev A ve Görev B):**
> *"30cm'de Servo1 sağa 90° döndürülür, Kırmızı Dikdörtgen payload
> bırakılır."* / *"30cm'de Servo1 SOLA 90° döndürülür, Mavi Dikdörtgen
> bırakılır."*

**Kod:** `core/config/parameters.py::PAYLOAD_APPROACH_ALTITUDES_M =
[10.0, 5.0, 0.45]` — bırakma **0.45 m**'de.

### ⚠️ DÜZELTME (2026-08-24): spec'in 0.30 m değeri BAYATTIR

Bu, sessiz bir kayma değil; **2026-08-17 tarihli, ölçüme dayalı operatör
revizyonudur**. Kanıt `parameters.py:365-377`'de birebir duruyor:

> *"OPERATÖR REVİZYONU (2026-08-17): son bırakma irtifası 0.30 m → 0.45 m.
> Yük artık düzleme 45 cm'den bırakılır. Ara adımlar (10 m, 5 m) ve
> PAYLOAD_FINAL_FORWARD_M (10 cm ileri kayma) değişmedi.*
>
> *Yan fayda (ADR-009 S1 ölçümü): merkezleme toleransı AÇISAL (normalize
> piksel), yani yere karşılığı irtifayla ölçeklenir — 0.30 m'de tolerans
> bandı yalnızca 3.6 mm iken CENTERING_MIN_CMD_SPEED_M_S tabanı tek
> iterasyonda 15 mm yol aldırıyordu (4.2x band). **V1' koşusunda her iki
> 0.30 m adımı da bu yüzden yakınsayamadı.** 0.45 m'de band 5.3 mm'ye
> çıkar, oran 4.2x → 2.8x'e düşer."*

Yani 0.30 m **fiziksel olarak yakınsayamıyordu**: kontrolcünün minimum
komut hızı, o irtifadaki tolerans bandından 4.2 kat büyük bir adım
attırıyordu. Değer ölçümle yükseltildi.

**Aynı sınıf bir karar Görev 3 tarafında da alındı** (bkz.
`payload/payload_config.py::FLEX-20`, 0.30 → 0.35 → 0.45): spec'in sayısı
ulaşılabilir bant dışında kalınca ölçümle revize edildi. İki bağımsız
alt sistemde aynı sonuca varılmış olması, sorunun spec'in sayısında
olduğunun ek göstergesidir.

**Sonuç:** kod doğru, spec belgesi güncellenmelidir. Kod değişikliği
gerekmiyor.

---

## SAPMA-02 — 1 m adımları: spec istiyor, ölçüm imkânsız diyor

**Spec md.7 / md.9:** 15→10→5→**1 m** kademeli görüntü-işlemeli merkezleme.
**Spec md.8 / md.10:** bırakma sonrası *"Drone **1m'ye** çıkar, lokal
doğrulama taraması açılır."*
**Spec md.14:** Görev 3'te 4→3→2→**1 m** merkezleme.

**Kod:** hiçbirinde 1 m adımı yok. Görev A/B `[10.0, 5.0, 0.45]`;
doğrulama bırakma irtifasında yapılıp doğrudan 15 m'ye tırmanılıyor
(`payload_release.py:271-281`); Görev 3 tek adımda 0.30 m'ye merkezleniyor.

### ⚠️ DÜZELTME (2026-08-24): 1 m'de görüntü işleme ÖLÇÜMLE GÜVENİLMEZ

`parameters.py:380-392` (ADR-010 P1), **ölçülmüş** veri:

> *"MEASURED, not assumed — V1''' koşusundan (mission_81cfefe66ad7), her
> merkezleme çağrısı için sürekli kaybın öncesindeki SON taahhüt edilmiş
> tespitin irtifası:*
> - *KIRMIZI_UCGEN 0.45 m adımı: 0.47 m'ye kadar izlendi (151 görüldü / 49 kayıp)*
> - ***MAVI_ALTIGEN 0.45 m adımı: 1.63 m'de kayboldu**, ilk ıskalama 1.47 m
>   (29 görüldü / 171 kayıp) → takıldı, 1.587 m'de bıraktı"*
>
> *"Sınır şekle bağlıdır çünkü kayıp GEOMETRİKtir, ayarlanabilir bir eşik
> değil: `_detect_hexagon` konturu TEK bir eps ile yaklaşıklıyor ve tam 6
> dışbükey köşe istiyor; altıgen kare kenarını kırptığı an konturu altıgen
> olmaktan çıkıyor."*
>
> `LOW_ALT_VISION_LIMIT_M = 2.0` — *"2.0 m gözlenen en yüksek kaybın
> (1.63 m) hemen üstünde, marjla."*

Spec'in **1 m'de merkezleme** ve **1 m'de lokal doğrulama taraması**
adımlarının ikisi de bu sınırın **altındadır**. Yani spec, vision'ın
ölçümle güvenilmez olduğu kanıtlanmış bölgede vision istiyor.

**ADR-010 bu düzeltmeyi açıkça kapsam dışı ilan etmiştir:**
> *"Detector gates are explicitly out of scope, so the fix is to stop
> REQUIRING vision below this altitude."*

Yani ADR-010'un çözümü detector'ı düzeltmek değil, **o irtifada vision'a
BAĞIMLI OLMAMAKtır** — kodun bugünkü davranışı tam olarak budur.

**Sonuç:** kod değişikliği YAPILMADI. Spec'in bu adımları uygulanmak
isteniyorsa önce detector'ın düşük irtifa davranışı düzeltilmelidir
(altıgen için çok-eps sweep veya kırpılmış kontur toleransı) — bu ayrı ve
bu projenin kapsamı dışında bir iştir. Etkisi
`payload/KNOWN_ISSUES.md` §6'da izleniyor.

---

## Kayıt dışı bırakılanlar

Denetim raporundaki diğer sapmalar (vision modlarının isimli enum
olmaması, state machine isim farkları, 5 m payload_reference'ın
kaydedilmemesi, Görev 3 kademeli merdiveni) bu dosyaya **alınmadı**:
bunlar "spec bayat" vakaları değil, henüz yapılmamış veya farklı
modellenmiş işlerdir. Durumları denetim raporunda ve
`parameters.py`'deki ilgili yorumlarda izleniyor.
