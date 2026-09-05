# GÖREV M — FAZ 1: manyetik ORYANTASYON düzeltmesi var mı?

**Tarih:** 2026-09-05 · **Kod değişikliği YOK** (salt analiz)
**Kaynaklar:** `src/modules/simulation/gz_plugins/hook_attach/HookAttachSystem.cc`,
`/opt/homebrew/include/gz/sim8/gz/sim/Link.hh`,
koşum `demo_20260905_153240_mission.log`, `docs/gorevK-P3-ab-sonuc.md`

---

## KESİN TEŞHİS

> **Oryantasyon düzeltme kuvveti YOK. "Var ama çalışmıyor" değil — hiç yazılmadı.**
> Mevcut model yalnızca **konum** çekimi yapar ve **yapısal olarak sıfır tork** üretir.

---

## 1 · Mevcut model tam olarak neyi simüle ediyor

`HookAttachSystem.cc` içindeki `MagnetForceSystem::PreUpdate`:

| satır | ne yapıyor |
|---|---|
| `:364-365` | kanca mıknatıs **noktası** = hook pozu + `Rot().RotateVector(0,0,-0.06565)` |
| `:376-377` | yük mıknatıs **noktası** = payload pozu + `Rot().RotateVector(0,0,+0.008)` |
| `:378` | `delta = pMagnet - hookMagnet` — iki **nokta** arası vektör |
| `:391` | `force = delta.Normalized() * fMag` |
| `:404` | `force -= vRel * damping_` — **doğrusal** hıza karşı sönümleme |
| `:408` | `hookLink.AddWorldForce(_ecm, force)` |
| `:412` | `payLink.AddWorldForce(_ecm, -force)` |

**İki bağımsız kanıt, oryantasyonun hiç hesaba girmediğini gösteriyor:**

**(a) Kullanılan API tork üretemez.** `Link.hh:332-337`:
> *"Add a force expressed in world coordinates and applied at the **center of mass** of the link."*

Kütle merkezine uygulanan kuvvetin gövdeye göre torku **tanım gereği sıfırdır**.
`Link.hh:355` bir `AddWorldWrench(ecm, force, **torque**)` sunuyor — **çağrılmıyor.**

**(b) Kuaterniyonlar yalnızca nokta konumlandırmak için okunuyor.** Dosyada
`Rot()` tam **iki** yerde geçiyor (`:365`, `:377`) ve ikisi de bir ofseti
döndürüp mıknatıs **noktasını** buluyor. Kanca ekseni ile yuva ekseni
arasındaki **açıya bağlı tek bir terim yok.** Sönümleme de `vRel`, yani
**doğrusal** hız — açısal hız (`ω`) hiç okunmuyor.

> Yani model şunu diyor: *"iki nokta birbirini çeker."* Gerçek mıknatısların
> yaptığı *"iki yüzey paralel olana kadar döner"* kısmı **yok.**

---

## 2 · Kanca fiziksel olarak neden yan yatıyor — **iki AYRI mekanizma**

### Ortak ön koşul: TEMAS
Serbest asılı kanca **0.005–0.9°** ölçüyor (`hook_seating.py`, ölçüm).
Bu oturumun inişlerinde de iniş boyunca **0.1–0.9°**. Yani kanca havadayken
sorun yok; eğim **her zaman burun bir yüzeye değdikten sonra** doğuyor.

### Mekanizma A — kordon gevşekliği (mıknatıstan ÖNCE de vardı)
Salım formülü `alt − 0.070 + 0.060 + 0.040`, geometrik gereken `alt − 0.02765`
⇒ **her zaman 57.7 mm fazla**. Burun değince fazlalık gevşekliğe dönüşür.
Araç SDF'i bunu zaten yazmış (`model.sdf:748-752`): *"her fazladan santim,
yerdeki kancayı deviren gevşekliğe dönüşür"* — ölçülmüş: ±0.7 rad → **77°**,
±1.2 rad → **49°**.

### Mekanizma B — mıknatısın kaldıraç etkisi (**YENİ**, bu koşumda ölçüldü)
`demo_20260905_153240`, deneme 1, zaman sırasıyla:

```
[ADAPTIF_INIS] BITTI ... lat= 27.3mm ins= -0.0mm tilt=  0.9deg     <- burun güvertede, kanca DİK
[HOOK] MIKNATIS CEKIM MENZILINDE: d=26.9 mm (<= 50.0 mm)           <- çekim başladı
[HOOK] APPROACHING lat= 26.9mm ins= +1.2mm tilt= 34.7deg
[HOOK] APPROACHING lat= 26.9mm ins= +1.5mm tilt= 42.0deg
[HOOK] APPROACHING lat= 27.2mm ins= +1.6mm tilt= 39.4deg
[HOOK] APPROACHING lat= 27.4mm ins= +1.9mm tilt= 40.9deg
```

**0.9° → 34.7°, çekimin başladığı örnekte.** Korelasyon bir saniyeden dar.

**Sebep:** kuvvet kütle merkezine uygulanıyor ama **burun güverte tarafından
tutuluyor**. Sabit bir temas noktası olan gövdeye kütle merkezinden uygulanan
kuvvet, **o temas noktası etrafında tork üretir.** Kanca kaymıyor, deviriliyor.

**Aynı kuvvetin serbest rejimde ne yaptığı da ölçüldü** — 42.1 mm boşlukta,
burun havadayken:
```
[MIKNATIS_BANDI] BITTI: yanal 29.2 mm -> 15.0 mm (+14.2 mm kazanc), 0.75 s
```
**Kapının (17.5 mm) içine girdi.** Karşılaştırma için eski taklit (aracı
oynatan model) 7 adımda 33.8 → 33.4 mm yapıyordu.

> **Sorunuza net cevap:** manyetik çekim kodu **yanlış bir tork uygulamıyor —
> HİÇ tork uygulamıyor.** Deviren torku Gazebo üretiyor: mıknatısın yanal
> kuvveti × temas kısıtı. Kod hatalı bir dönme değil, **eksik bir dönme**
> içeriyor.

---

## 3 · Ekran görüntüsü ile probe'un "165–169°" anomalisi **AYNI DEĞİL**

| | probe anomalisi (P2) | ekran görüntüsü / bugünkü koşum |
|---|---|---|
| burun konumu | `nose_z = −0.0987` — **zeminin 10 cm ALTINDA** | `ins = +1.2…+2.8 mm` — **güvertenin üstünde** |
| zincir | patlamış: `span` 0.235 → **0.094**, `fold` 68°'ye kadar | sağlam |
| sebep | **probe sıra hatası**: 0.30 m'ye inip SONRA salım → burun yere sürüldü | **mıknatıs kaldıracı** (Mekanizma B) |
| durum | **düzeltildi** (probe görevin sırasını izliyor) | **açık** |
| eğim | 153–169° (devrilmiş/ters) | 30–44° |

**Ayrı gözlemler.** Ortak yanları yalnızca §2'deki ön koşul: ikisi de burun
bir yüzeye kısıtlandıktan sonra oluşuyor. Kök nedenler farklı.

---

## 4 · FAZ 2 için hazır olan şeyler (uygulanmadı)

- **API mevcut:** `Link::AddWorldWrench(ecm, force, torque)` — `Link.hh:355`.
- **Fiziksel doğru biçim** dipol hizalama torkudur, `τ = m × B`, yani
  `τ = k · (â_kanca × â_yuva) − c_ω · ω_bağıl`.
  Çapraz çarpım `sin(θ)` ile orantılıdır: **hizaya yaklaştıkça kendiliğinden
  yumuşar** — operatörün istediği "ani/sert değil, kademeli hizalanma"
  davranışı modelin kendisinden çıkar, ayrıca kazanç profili gerekmez.
- **Kazanç ölçümden türetilmeli**, seçilmemeli: kancanın atalet momenti,
  ölçülen sarkaç periyodu (1.078 s, Görev J) ve 8° tilt kapısı elde var.
- 8° kapısı **gevşetilmeyecek**; hedef kancanın o kapıya kendi girmesi.

---

## 5 · ÇAKIŞMA — operatöre soru

Görev K'nın adaptif alçalması **irtifayı**, Görev M **eğimi** düzeltecek ve
ikisi aynı 5 cm menzilinde çalışıyor. Sıra/öncelik bir karar gerektiriyor;
FAZ 2'ye geçmeden soruyorum (§ ayrı mesaj).

Ölçümün şu ana kadar söylediği, seçeneği daraltıyor:
- Kanca **serbest** iken mıknatıs işini yapıyor (29.2 → 15.0 mm).
- Kanca **temasta** iken aynı kuvvet onu deviriyor (0.9° → 42°).

Yani tork, **temastan önce** devrede olursa kancayı dik tutar; **temastan
sonra** devreye girerse çoktan devrilmiş bir kancayı düzeltmeye çalışır.
