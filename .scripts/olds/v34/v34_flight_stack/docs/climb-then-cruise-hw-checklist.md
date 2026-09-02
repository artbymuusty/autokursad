# Climb-then-Cruise — Gerçek Donanım Öncesi Kontrol Listesi

**Durum:** Bu özellik yalnızca Gazebo SITL'de doğrulanmıştır. Aşağıdaki adımlar
tamamlanmadan gerçek araçta **uçurulmamalıdır.**

İlgili: [flight-control-analysis.md](flight-control-analysis.md) · `core/navigation/motion_fsm.py`

---

## 1. Eşik kalibrasyonu — ZORUNLU, atlanamaz

`real_system.yaml` içindeki `motion_profile` değerlerinin tamamı **tahmindir**
ve `TODO` ile işaretlidir. İkisi doğrudan sensör gürültü tabanına oturur ve
kalibre edilmeden uçurulursa state makinesi **hiç ilerlemez**:

| Parametre | Neden kritik | Yanlışsa ne olur |
|---|---|---|
| `vz_settle_m_s` | Gerçek barometre/EKF dikey hız gürültüsü SITL'den yüksek | Guard hiç geçmez → CLIMB `vertical_timeout_s`'te (20 s) zaman aşımına uğrar, bacak başarısız |
| `attitude_rate_limit_deg_s` | Gerçek IMU gürültüsü + rotor titreşimi | HOLD hiç "durulmuş" demez → her bacakta `hold_max_s` (5 s) yenir, 600 s bütçe erir |

**Yöntem:**
1. Aracı arm edip **havada sabit hover'da** tut (Offboard'a girmeden, HOLD modunda).
2. `MOTION_STATE_CHANGED` / `MOTION_HOLD_SETTLED` olaylarını değil, doğrudan
   telemetriyi kaydet: 60 s boyunca `get_velocity_ned()[2]` ve
   `get_attitude_euler()` roll/pitch.
3. Taban gürültüyü ölç: `vz` için p95 |değer|, attitude için ardışık örnek
   farkından türetilen p95 rate.
4. Eşiği ölçülen p95'in **~3 katına** koy.
5. Ölçüm koşumunu `logs/` altına kaydet ve YAML yorumuna tarihi yaz.

> Kalibrasyon öncesi bir "deneme uçuşu" yapılacaksa `motion_profile.enabled: false`
> ile yapılmalı — o zaman `goto_waypoint()` eski `goto_global_position_and_wait()`
> davranışına düşer ve bilinen bir zeminde uçulur.

## 2. Bütçe doğrulaması

- `MISSION_TIMEOUT` = **600 s** ve Şartname Bölüm 5.6 gereği **zorunludur**.
- HOLD artık sabit değil guard'lı: gerçek araçta SITL'den **uzun sürer**.
- Her bacakta `MOTION_HOLD_SETTLED` olayı `cumulative_hold_s` ve
  `cumulative_hold_pct_of_budget` yayınlıyor. **İlk gerçek uçuşta bu değeri izle.**
- Referans (SITL, 2026-09-02): Görev 2 bağlantıdan `GOREV2_COMPLETE`'e 206 s.
  Görev 2'de iki payload bacağı var → 2 × (HOLD + ARRIVAL_HOLD).
- `cumulative_hold_pct_of_budget` %5'i aşıyorsa `hold_max_s` ve
  `arrival_hold_s` gözden geçirilmeli.

## 3. Offboard sürekliliği

- PX4 ~500 ms setpoint'siz kalırsa Offboard'dan düşer. Bu kod tabanında bunun
  en az dört ayrı BUG FIX kaydı var.
- FSM her state'te 10 Hz akış sürdürür ve state geçişleri aynı çağrı zincirinde
  olur — arada bekleme yoktur. Birim testi bunu zorluyor
  (`test_every_state_streams_setpoints_including_hold`).
- **Gerçek uçuşta doğrula:** telemetri linki SITL'den yavaş. `get_position_ned()`
  + `get_global_position()` + `get_velocity_ned()` + `get_yaw_deg()` çağrıları
  CRUISE döngüsünde **tick başına dört ayrı await** demek. Link gecikmesi
  yüksekse tick 100 ms'i aşabilir.
- İlk uçuşta `telemetry_stream_rates()` çıktısını kaydet; gözlenen Hz 5'in
  altındaysa CRUISE döngüsündeki telemetri çağrıları tek bir snapshot'a
  indirilmeli (bu PR'da yapılmadı — SITL'de gerek görülmedi).

## 4. Değişmediği doğrulanacaklar

Bu çalışma bilerek dar tutuldu. Gerçek uçuş öncesi bunların **değişmediğini**
teyit et:

- [ ] `go_to_and_center()` — dokunulmadı. Üç eksenli kuplajı kasıtlı
      (ADR-009/010, kademeli iniş alçalırken merkezler).
- [ ] `goto_global_position_and_wait()` — dokunulmadı, hâlâ Görev 3 fazlarında
      ve dönüş bacağında kullanılıyor.
- [ ] Görev 3 fazları — hiçbiri yeni yola geçirilmedi.
- [ ] `MISSION_TIMEOUT` watchdog'u — tek armed watchdog, korundu.
- [ ] Geofence / batarya failsafe — **eklenmedi** (bu kod tabanında zaten yok,
      PX4 tarafına bırakılmış durumda; bu PR o politikayı değiştirmiyor).
- [ ] PX4 `MPC_*` parametreleri — proje hâlâ hiçbirini set etmiyor.

## 5. İlk gerçek uçuş protokolü

1. `motion_profile.enabled: false` ile bir referans uçuş — eski davranış, taban.
2. Hover ölçümü (§1) → eşikleri YAML'a yaz → commit.
3. `enabled: true`, **tek bacak**, geniş açık alan, RC pilot hazır.
4. `MOTION_STATE_CHANGED` sırasını logdan doğrula: CLIMB → HOLD → CRUISE →
   (DESCEND) → ARRIVAL_HOLD.
5. Eksen ayrımını doğrula: CLIMB sırasında yatay hareket **görülmemeli**.
6. Ancak bundan sonra tam görev.

## 6. Bilinen sınırlar

- `ned_to_body()` her tick'te güncel yaw ile dönüşüm yapıyor. Araç CRUISE
  sırasında yaw değiştirirse (rüzgar ağırlıklı) komut yönü takip eder; bu
  doğru ama yaw hızlı dönerse yatay komut titreyebilir. SITL'de gözlenmedi.
- Trapez profil `accel_m_s2` ile `SETPOINT_MAX_DELTA_V_M_S`/tick aynı olacak
  şekilde seçildi. `real_system.yaml`'da `accel_m_s2: 1.0` verildi ama
  `SETPOINT_MAX_DELTA_V_M_S` hâlâ 0.15 (=1.5 m/s²) — yani gerçek profilde
  **fren profili değil limiter** baskın olacak. Bu bilinçli (muhafazakâr),
  ama kalibrasyonda gözden geçirilmeli.
- Entegrasyon testi yalnızca **Görev 2 bacağını** kapsıyor. Görev 3 Faz 1
  ayrı iş kalemi.
