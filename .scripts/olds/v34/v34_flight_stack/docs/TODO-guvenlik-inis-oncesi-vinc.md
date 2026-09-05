# TODO — GÜVENLİK: iniş öncesi vinç toplama ZORUNLU

**Açılış:** 2026-09-05 (GÖREV K / D ölçüm koşumu sırasında bulundu)
**Durum: AÇIK** · **Öncelik: YÜKSEK (H maddesinin ÖN KOŞULU)**
**Operatör kararı (2026-09-05):** ayrı ve öncelikli güvenlik maddesi olarak
işaretlenecek; H (dönüş/iniş stratejisi) uygulanırken ön koşul olarak eklenecek.

---

## 1 · Ne oldu (ölçüm, tahmin değil)

`tools/magnet_attract_probe.py`'ın ilk koşumu 10 dakikalık zaman aşımıyla
**uçuş ortasında öldürüldü**. Araç Offboard modunda setpoint akışı kesilince
failsafe ile inişe geçti — **vinç AÇIKTI**. Kanca (base_link'in 31 cm altında,
vinç salımıyla daha da aşağıda) iniş takımından önce yere değdi, prizmatik
vinç eklemi ezildi ve fizik çözücüsü infilak etti:

```
ODE INTERNAL ERROR 1: assertion "aabbBound >= dMinIntExact &&
aabbBound < dMaxIntExact" failed in collide() [collision_space.cpp:460]
Stack trace: ... GzOdeCollisionDetector::collide ...
             dart::constraint::ConstraintSolver::solve()
```

`aabbBound` iddiası, bir gövdenin sınır kutusunun NaN/sonsuza gitmesi
demektir — yani kısıtlama çözümü patlamış. Gazebo süreci `abort()` ile öldü.

**KAPSAM KONTROLÜ:** beş demo koşumunun (`demo/runs/2026090*`) `sitl.log`
dosyalarında bu izden **hiçbiri yok** — arıza yalnızca vinç açıkken inişe
geçilen bu senaryoda oluştu. Yani mevcut demo arızalarının (tespit) sebebi
değil, AYRI bir risk.

## 2 · Neden gerçek bir risk (yalnızca probe'a özgü değil)

Depoda vinç toplama zaten biliniyor ve YORUMDA da yazıyor:

> `gz_payload_actuator.py`: *"Vinç, yük BIRAKILDIKTAN sonra
> activate_drop_mechanism içinde toplanır -- inişden önce toplanmazsa
> kanca yere iniş takımından önce değer."*

Ama bu, **normal alma/bırakma akışına bağlı**. Vinç açıkken inişe götüren
YOLLAR bunun dışında da var:

| Yol | Kod | Vinç toplanıyor mu |
|---|---|---|
| Normal görev sonu iniş | `master_fsm._land()` → `flight.land()` (satır 330-334) | **Kontrol edilmiyor** |
| Görev 3 başarısız → dönüş+iniş | `master_fsm` LANDING geçişi | **Kontrol edilmiyor** |
| Ctrl-C / SIGTERM (ADR-010 R4) | `core/runtime/shutdown.py` → araç başlangıç noktasına dönüp iner | **Kontrol edilmiyor** |
| PX4 failsafe (setpoint kesilmesi, batarya, link) | PX4'ün kendi iniş mantığı | **Uygulama hiç haberdar değil** |
| Alma denemesi ortasında faz iptali | `_await_seating` timeout yolları vinci topluyor, ama iptal (`CancelledError`) yolu **belirsiz** | Kısmen |

Son satır özellikle önemli: son dördü de "yük bırakılmadan" iniş anlamına
geliyor, yani `activate_drop_mechanism`'in toplama adımı hiç çalışmıyor.

## 3 · Yapılması gerekenler (H maddesinin ön koşulu)

1. **Tek kapı:** inişi başlatan HER yol, önce `set_winch(HOOK_WINCH_RETRACT_M)`
   çağırıp toplanmayı **doğrulamalı** (komutun döndüğüne değil, `winch_state()`
   ölçümüne bakarak — 2026-08-23'te öğrenilen "sonucu doğrula, komutu değil"
   kuralı).
2. **Yeri:** `master_fsm._land()` içi doğru yer — LANDING geçişinden ÖNCE.
   Böylece normal bitiş, Görev 3 başarısızlığı ve sinyal yolu tek noktadan
   korunur.
3. **Failsafe:** PX4'ün kendi failsafe inişini uygulama durduramaz; bu yüzden
   vinç **yalnızca gerçekten gerekli olduğu pencerede** açık kalmalı
   (alma/bırakma), pencere biter bitmez toplanmalı. "Taşıma boyunca vinç açık
   kalsın" kararı (2026-08-21, operatör) bu riskle birlikte yeniden
   değerlendirilmeli — taşıma sırasında bir failsafe inişi aynı ezilmeyi verir.
4. **Test:** vinç açıkken `_land()` çağrılırsa toplama çağrısının yapıldığını
   ve toplanma doğrulanmadan `flight.land()`'e geçilmediğini kilitleyen bir
   test.

## 4 · Şimdilik yapılan

- `tools/magnet_attract_probe.py` içine `finally: set_winch(RETRACT)` eklendi
  ve gerekçesi koda yazıldı. **Bu yalnızca ölçüm aracını korur**, görev
  akışını korumaz — yukarıdaki 4 madde hâlâ açık.
