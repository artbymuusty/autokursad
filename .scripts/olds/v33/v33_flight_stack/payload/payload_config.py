"""PHASE 3: FLEX Registry.

Bu dosya, payload/ paketindeki HER esnek fiziksel parametrenin tek kaynağı.
Kural kesin: payload/ içindeki hiçbir dosyada bu dosyadan import edilmeyen
"gizli" bir sayı (magic number) OLMAYACAK. Bir ölçü/süre/mesafe görürsen ve
kaynağı burada bir FLEX-XX değilse, bu bir hatadır.

Bilinmeyen değerler (bench test gerektirenler) sessizce tahmin EDİLMEDİ --
açıkça None olarak bırakıldı ve TBD olarak işaretlendi. None'ı gerçek bir
sayı gibi kullanmaya çalışan kod (ör. bir backend implementasyonu) doğal bir
TypeError ile patlar -- bu kasıtlı: kalibre edilmemiş bir değerin sessizce
0 veya "makul bir tahmin" gibi davranmasındansa gürültülü şekilde durması
tercih edilir.
"""
from typing import Optional, Tuple

# ============================================================
# TODO(ARCHITECTURE-DECISION) — payload/ vs. IPayloadActuator
#
# Bu payload/ paketi, real_system/real_payload_actuator.py
# (IPayloadActuator) yolunun yerini almak üzere tasarlandı (supersede
# kararı alındı). Bu dosyaya bu fazda dokunulmuyor/import edilmiyor.
# Gerçek migrasyon (gorev3_pickup.py'nin payload_manager'a bağlanması)
# ayrı bir MissionManager wiring fazında yapılacak.
# ============================================================


# ============================================================
# FLEX-01 — HOOK CAPTURE DISTANCE / ENVELOPE
#
# WHY FLEXIBLE:
# Kancanın payload'ı "yakaladı" sayılması için payload'a ne kadar
# yaklaşması gerektiği, kanca geometrisine, manyetik alan menziline ve
# kamera/sensör toleransına bağlı -- sahada ölçülmeden bilinemez.
#
# REAL-WORLD TEST NEEDED:
# Bench test: kanca farklı mesafelerden payload'a yaklaştırılıp hangi
# mesafede fiziksel/manyetik temas güvenilir şekilde kuruluyor ölçülmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli. Repoda veya kullanıcı mesajında bu değeri
# destekleyen bir kaynak yok.
#
# NOT (2026-08-23, PHASE 5 — DOĞRULANMAMIŞ GÖZLEM, TEŞHİS DEĞİL):
# 2026-08-21 tarihli 6 SITL koşusunda /hook/attach sonrası
# [CATCH_PAYLOAD_TIMEOUT] 15.0s gözlendi (.scripts/olds/v33/logs/
# mission_20260821_*.log). Aynı koşuların gz sunucu loglarında hiç
# "[HookAttach]" satırı YOK (~/.gz/sim/log/2026-08-21T*/server_console.log);
# buna karşılık 2026-08-20T20:55:43 oturumunda 16 satır var ve attach
# isteği ile ATTACHED arası 2.2 ms ölçülüyor. Ayrıca HookAttachSystem.cc
# hiçbir mesafe/poz kontrolü YAPMIYOR (232 satırda tek bir Pose component
# okuması yok). Bu bir GÖZLEMDİR; kök neden analizi YAPILMADI. Bu FLEX'in
# değeri hakkında hiçbir şey söylemez ve envelope'un yetersiz olduğuna
# dair kanıt DEĞİLDİR -- buraya sadece, kalibrasyon sırasında bu timeout
# loglarının yanlışlıkla "envelope yetersiz" kanıtı olarak okunmaması
# için yazıldı.
#
# AFFECTS:
# PayloadBackend.is_in_capture_zone() implementasyonu (PHASE 4/5).
#
# HOW TO CALIBRATE:
# Kancayı payload'a kademeli mesafelerle yaklaştır, her mesafede yakalama
# başarı oranını kaydet; güvenilir (>%95) yakalama başlayan en büyük
# mesafeyi envelope olarak al.
# ============================================================
FLEX_01_HOOK_CAPTURE_ENVELOPE_M: Optional[float] = None


# ============================================================
# FLEX-02 — HOOK DEPLOYMENT TIME
#
# WHY FLEXIBLE:
# Servo2'nin kancayı tam indirme süresi, servo torku/yüküne ve mekanik
# sürtünmeye bağlı -- gerçek donanımda ölçülmeden varsayılamaz.
#
# REAL-WORLD TEST NEEDED:
# Bench test: SERVO2_DOWN komutundan kancanın tam açılmış konuma
# ulaşmasına kadar geçen süre kronometre/encoder ile ölçülmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# PayloadBackend.deploy() timeout bütçesi (PHASE 4/5).
#
# HOW TO CALIBRATE:
# En az 10 tekrar ölç, ortalama + güvenlik payı (örn. %50 marj) al.
# ============================================================
FLEX_02_HOOK_DEPLOYMENT_TIME_S: Optional[float] = None


# ============================================================
# FLEX-03 — MAGNETIC CAPTURE CONFIRMATION DELAY
#
# WHY FLEXIBLE:
# Manyetik temasın "gerçekten kuruldu" olarak doğrulanması için sensör
# okumasının kaç örnek/kaç ms boyunca stabil kalması gerektiği, sensör
# gürültüsüne bağlı -- sahada karakterize edilmeli.
#
# REAL-WORLD TEST NEEDED:
# Bench test: manyetik sensör çıktısının temas anındaki gürültü/sıçrama
# profili kaydedilip debounce süresi buradan türetilmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# PayloadBackend.has_captured() / await_capture() implementasyonu
# (PHASE 4).
#
# HOW TO CALIBRATE:
# Sensör logunu temas anında yüksek frekansta kaydet, sıçrama süresinin
# üstünde bir debounce penceresi seç.
# ============================================================
FLEX_03_MAGNETIC_CAPTURE_CONFIRM_DELAY_S: Optional[float] = None


# ============================================================
# FLEX-04 — GRAPPLE ACTIVATION DELAY
#
# WHY FLEXIBLE:
# Servo3'ün kavrama komutunu aldıktan sonra fiziksel olarak kavramayı
# tamamlamasına kadar geçen süre, mekanizmanın gerçek hızına bağlı.
#
# REAL-WORLD TEST NEEDED:
# Bench test: SERVO3_GRAPPLE komutundan kavrama tamamlanana kadar geçen
# süre ölçülmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# PayloadBackend.grapple() timeout bütçesi (PHASE 4/5).
#
# HOW TO CALIBRATE:
# En az 10 tekrar ölç, ortalama + güvenlik payı al.
# ============================================================
FLEX_04_GRAPPLE_ACTIVATION_DELAY_S: Optional[float] = None


# ============================================================
# FLEX-05 — PAYLOAD STABILIZATION / RETRACT DISTANCE
#
# WHY FLEXIBLE:
# Payload'ın geri çekme sırasında sallanmadan/salınmadan stabil hale
# gelmesi için kancanın ne kadar geri çekilmesi gerektiği, payload
# ağırlığı/ip uzunluğuna bağlı.
#
# REAL-WORLD TEST NEEDED:
# Bench/uçuş testi: farklı retract mesafelerinde payload salınımı gözle/
# IMU ile ölçülmeli, salınımın kabul edilebilir seviyeye düştüğü mesafe
# belirlenmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# PayloadBackend.retract() hedef mesafesi (PHASE 4/5).
#
# HOW TO CALIBRATE:
# Yüklü retract sonrası salınım genliğini video/IMU ile ölç, genliğin
# kabul edilebilir eşiğin altına düştüğü retract mesafesini seç.
# ============================================================
FLEX_05_STABILIZATION_RETRACT_DISTANCE_M: Optional[float] = None


# ============================================================
# FLEX-06 — CAPTURE TIMEOUT
#
# WHY FLEXIBLE:
# Yakalama denemesinin ne kadar süre bekleneceği, rüzgar/hizalama
# hatası gibi saha koşullarına göre ayarlanabilir olmalı.
#
# REAL-WORLD TEST NEEDED:
# Zaten V33 dokümanında sabitlenmiş bir değer var; ek saha testi sadece
# bu değerin gerçek donanımda hâlâ yeterli olduğunu doğrulamak için
# gerekebilir.
#
# CURRENT DEFAULT:
# 15.0 saniye — kullanıcı tarafından bu görev talimatında verildi
# ("V33: 15 s"), mevcut kodda da aynı değer var
# (core/config/parameters.py::V3_CATCH_PAYLOAD_TIMEOUT_S = 15.0,
# gz_system/gz_payload_actuator.py'nin mevcut, bu pakete BAĞLANMAMIŞ
# CATCH_PAYLOAD_TIMEOUT davranışıyla da tutarlı).
#
# AFFECTS:
# PayloadBackend.await_capture(timeout_s=...) çağrısına geçirilecek
# bütçe (PHASE 4/5); PayloadManager.catch_box_down()'ın SEARCHING ->
# CAPTURE_TIMEOUT geçiş kararı.
#
# HOW TO CALIBRATE:
# Gerekirse: saha testinde gerçek yakalama sürelerinin dağılımını ölç,
# 15.0s'nin p99 üstünde kalıp kalmadığını doğrula.
# ============================================================
FLEX_06_CAPTURE_TIMEOUT_S: float = 15.0


# ============================================================
# FLEX-07 — RELEASE HEIGHT
#
# WHY FLEXIBLE:
# Payload'ın bırakılacağı irtifa, payload ağırlığı/düşüş
# karakteristiğine ve hedef isabet toleransına göre ayarlanabilir olmalı.
#
# REAL-WORLD TEST NEEDED:
# Zaten V33 dokümanında sabitlenmiş bir değer var; ek saha/uçuş testi bu
# irtifadan bırakılan payload'un isabet dağılımını doğrulamak için
# kullanılabilir.
#
# CURRENT DEFAULT:
# 0.45 metre (45 cm) — kullanıcı tarafından bu görev talimatında verildi
# ("V33: 45 cm"). Not: mevcut, bu pakete BAĞLANMAMIŞ Görev 3 kodundaki
# core/config/parameters.py::GOREV3_DESCENT_ALTITUDE_M = 0.30 farklı bir
# fazın (pickup yaklaşma irtifası) değeridir, bu FLEX-07 ile
# karıştırılmamalı -- bu ayrı bir aşamanın (release) irtifasıdır.
#
# AFFECTS:
# PayloadManager.release() öncesi mission'ın ineceği hedef irtifa
# (bu paket dışında, mission katmanında kullanılacak).
#
# HOW TO CALIBRATE:
# Farklı irtifalardan bırakılan payload'ların hedefe göre sapmasını ölç,
# en düşük sapmayı veren irtifayı seç.
# ============================================================
FLEX_07_RELEASE_HEIGHT_M: float = 0.45


# ============================================================
# FLEX-08 — RELEASE SEQUENCE TIMING
#
# WHY FLEXIBLE:
# SERVO3_RELEASE komutundan payload'ın fiziksel olarak ayrılmasına kadar
# geçen süre, mekanizma hızına ve payload ataletine bağlı.
#
# REAL-WORLD TEST NEEDED:
# Bench test: bırakma komutu ile payload'ın fiziksel ayrılışı arasındaki
# gecikme ölçülmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# PayloadBackend.release() timeout bütçesi (PHASE 4/5).
#
# HOW TO CALIBRATE:
# En az 10 tekrar ölç, ortalama + güvenlik payı al.
# ============================================================
FLEX_08_RELEASE_SEQUENCE_TIMING_S: Optional[float] = None


# ============================================================
# FLEX-09 — HOOK-TO-PAYLOAD ALIGNMENT OFFSET (X/Y/Z)
#
# WHY FLEXIBLE:
# Kanca ile payload'ın gerçek montaj/kamera-lever-arm ofseti, mekanik
# montaja bağlı ve donanım revizyonuyla değişebilir.
#
# REAL-WORLD TEST NEEDED:
# Fiziksel ölçüm: kanca merkezinden payload yakalama noktasına olan X/Y/Z
# mesafesi cetvel/CAD model ile ölçülmeli.
#
# CURRENT DEFAULT:
# (0.0, 0.0, 0.0) — kullanıcı tarafından bu görev talimatında açık
# default olarak verildi ("default 0.0/0.0/0.0"). Bu, "ofset yok/bilinmiyor"
# anlamına gelir, "ofset ölçüldü ve sıfır çıktı" anlamına GELMEZ.
#
# AFFECTS:
# PayloadBackend.is_in_capture_zone() konum hesaplaması (PHASE 4/5).
#
# HOW TO CALIBRATE:
# Kanca ve payload yakalama noktasının CAD/fiziksel ölçümüyle X/Y/Z
# ofsetini belirle.
# ============================================================
FLEX_09_HOOK_TO_PAYLOAD_OFFSET_XYZ_M: Tuple[float, float, float] = (0.0, 0.0, 0.0)


# ============================================================
# FLEX-10 — GRAPPLE CONFIRMATION DELAY
#
# WHY FLEXIBLE:
# Kavramanın "gerçekten kuruldu" olarak doğrulanması için sensör/servo
# state okumasının ne kadar stabil kalması gerektiği donanıma bağlı.
#
# REAL-WORLD TEST NEEDED:
# Bench test: kavrama anındaki sensör/servo state sıçrama profili
# kaydedilip debounce süresi türetilmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# PayloadBackend.is_grappled() implementasyonu (PHASE 4/5).
#
# HOW TO CALIBRATE:
# Sensör logunu kavrama anında yüksek frekansta kaydet, sıçrama süresinin
# üstünde bir debounce penceresi seç.
# ============================================================
FLEX_10_GRAPPLE_CONFIRM_DELAY_S: Optional[float] = None


# ============================================================
# FLEX-11 — GRAPPLE TIMEOUT
#
# WHY FLEXIBLE:
# Kavrama denemesinin ne kadar süre bekleneceği, mekanizma hızına ve
# saha koşullarına göre ayarlanabilir olmalı.
#
# REAL-WORLD TEST NEEDED:
# Bench test: gerçek kavrama sürelerinin dağılımı ölçülüp timeout bu
# dağılımın üstünde seçilmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli. (FLEX-06'nın aksine V33 dokümanında/kullanıcı
# mesajında bu değer için bir referans verilmedi.)
#
# AFFECTS:
# PayloadManager.grapple()'ın GRAPPLING -> GRAPPLE_TIMEOUT geçiş kararı.
#
# HOW TO CALIBRATE:
# FLEX-04 ölçümüyle birlikte: ortalama aktivasyon gecikmesi + güvenlik
# payı.
# ============================================================
FLEX_11_GRAPPLE_TIMEOUT_S: Optional[float] = None


# ============================================================
# FLEX-12 — PAYLOAD SECURED RELATIVE POSITION
#
# WHY FLEXIBLE:
# Payload "güvenceye alındı" (SECURED) sayıldığında kanca gövdesine göre
# hangi göreli konumda asılı durması beklendiği, ip/kanca geometrisine
# bağlı.
#
# REAL-WORLD TEST NEEDED:
# Bench test: retract tamamlandığında payload'ın gövdeye göre X/Y/Z
# konumu ölçülmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# PayloadBackend.is_secured() implementasyonu (PHASE 4/5).
#
# HOW TO CALIBRATE:
# Retract sonrası payload konumunu CAD/fiziksel ölçümle X/Y/Z olarak
# belirle.
# ============================================================
FLEX_12_PAYLOAD_SECURED_RELATIVE_POSITION_XYZ_M: Optional[Tuple[float, float, float]] = None


# ============================================================
# FLEX-13 — RETRACT TIMEOUT
#
# WHY FLEXIBLE:
# retract() işleminin (V33: SERVO2_REVERSE, 1. kullanım) ne kadar sürede
# tamamlanması beklendiği, payload ağırlığına ve mekanizma hızına bağlı --
# bu SÜREdir, FLEX-05'in taşıdığı mesafe (kaç metre geri çekileceği) ile
# KASITLI OLARAK coupling yapılmamıştır (ikisi bağımsız ölçülüp bağımsız
# kalibre edilir: biri "ne kadar", diğeri "ne sürede").
#
# REAL-WORLD TEST NEEDED:
# Bench test: retract() komutundan RETRACTING -> SECURED doğrulamasının
# gerçekleştiği ana kadar geçen süre ölçülmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli. (2026-08-22 kullanıcı kararı: FLEX-05'ten
# ayrı bir numara olarak eklendi, PayloadManager.catch_box_up()'ın önceki
# turdaki timeout=None geçici çözümünün yerini alıyor.)
#
# AFFECTS:
# PayloadManager.catch_box_up()'ın retract() çağrısını sarmalayan
# asyncio.wait_for bütçesi; RETRACTING -> RETRACT_TIMEOUT geçiş kararı.
#
# HOW TO CALIBRATE:
# En az 10 tekrar ölç, ortalama + güvenlik payı (örn. %50 marj) al --
# FLEX-02/FLEX-04/FLEX-08 ile aynı yöntem.
# ============================================================
FLEX_13_RETRACT_TIMEOUT_S: Optional[float] = None


# ============================================================
# TODO(CONFIG-SYNC) — FLEX-14 / FLEX-15 ile real_system.yaml çakışması
#
# real_system/config/real_system.yaml içinde
# mission_v3.servo2_actuator_channel / servo3_actuator_channel zaten null
# olarak tanımlı ve bu FLEX-14/15 ile çakışıyor. payload_config.py tek
# otorite kalır, yaml'a bu fazda dokunulmuyor. Phase 16 bench
# kalibrasyonunda iki kaynak tek kaynağa (payload_config.py) indirilecek,
# yaml alanları kaldırılacak veya buradan otomatik üretilecek.
#
# Bu not, aşağıdaki FLEX-14 ve FLEX-15 bloklarının HER İKİSİ için de
# geçerlidir.
# ============================================================


# ============================================================
# FLEX-14 — SERVO2 ACTUATOR INDEX
#
# WHY FLEXIBLE:
# Servo2'nin (kanca indirme/geri çekme -- V33 SERVO2_DOWN ve
# SERVO2_REVERSE) flight controller üzerinde hangi actuator index'ine
# bağlandığı, uçuş kartının AUX/MAIN kablolamasına ve PX4 çıkış
# haritasına bağlı -- fiziksel montaj yapılmadan bilinemez.
#
# REAL-WORLD TEST NEEDED:
# Bench test: servo kabloları takıldıktan sonra her actuator index'i
# tek tek sürülüp Servo2'nin fiziksel olarak hangisinde hareket ettiği
# doğrulanmalı.
#
# CURRENT DEFAULT:
# TBD — donanım montajı/bench test gerekli. (real_system.yaml'daki
# servo2_actuator_channel de aynı şekilde null; bkz. yukarıdaki
# TODO(CONFIG-SYNC).)
#
# AFFECTS:
# RealPayloadBackend.deploy() / retract() / stow() -- üçü de
# Action.set_actuator(index=FLEX-14, ...) çağırır. CALIBRATION GUARD:
# bu değer None iken bu üç metod set_actuator'a HİÇ ulaşmadan
# PayloadCalibrationError ile durur.
#
# HOW TO CALIBRATE:
# MAVSDK Action.set_actuator(index, value) ile index'leri 1'den
# başlayarak tek tek sür, Servo2'nin hareket ettiği index'i kaydet.
# NOT: MAVSDK'da actuator index 1'den başlar (0'dan DEĞİL).
# ============================================================
FLEX_14_SERVO2_ACTUATOR_INDEX: Optional[int] = None


# ============================================================
# FLEX-15 — SERVO3 ACTUATOR INDEX
#
# WHY FLEXIBLE:
# Servo3'ün (kavrama/bırakma -- V33 SERVO3_GRAPPLE ve SERVO3_RELEASE)
# flight controller üzerindeki actuator index'i, FLEX-14 ile aynı
# nedenle montaja bağlı.
#
# REAL-WORLD TEST NEEDED:
# Bench test: FLEX-14 ile aynı yöntem -- index'ler tek tek sürülüp
# Servo3'ün hangisinde hareket ettiği doğrulanmalı.
#
# CURRENT DEFAULT:
# TBD — donanım montajı/bench test gerekli. (real_system.yaml'daki
# servo3_actuator_channel de aynı şekilde null; bkz. yukarıdaki
# TODO(CONFIG-SYNC).)
#
# AFFECTS:
# RealPayloadBackend.grapple() / release() -- ikisi de
# Action.set_actuator(index=FLEX-15, ...) çağırır. CALIBRATION GUARD:
# bu değer None iken bu iki metod set_actuator'a HİÇ ulaşmadan
# PayloadCalibrationError ile durur.
#
# HOW TO CALIBRATE:
# FLEX-14 ile aynı prosedür. NOT: index 1'den başlar.
# ============================================================
FLEX_15_SERVO3_ACTUATOR_INDEX: Optional[int] = None


# ============================================================
# FLEX-16 — SERVO2 DOWN VALUE (kanca indirme)
#
# WHY FLEXIBLE:
# Kancayı "tam inmiş" konuma götüren normalize actuator değeri
# (-1..1), servo tipine, montaj yönüne ve mekanik son duraklara bağlı.
# Yanlış değer servoyu mekanik sınıra dayayıp donanıma zarar verebilir.
#
# REAL-WORLD TEST NEEDED:
# Bench test: servo yüksüzken küçük adımlarla sürülüp kancanın tam
# indiği ve mekanik sınıra DAYANMADIĞI değer bulunmalı.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli. Tahmin edilmedi: kalibre edilmemiş bir
# actuator değeri fiziksel hasar riskidir (bkz. CALIBRATION GUARD).
#
# AFFECTS:
# RealPayloadBackend.deploy() (V33: SERVO2_DOWN).
#
# HOW TO CALIBRATE:
# 0.0'dan başlayıp hedef yönde 0.05'lik adımlarla ilerle, her adımda
# kancanın konumunu gözle; tam açık konuma ulaşan İLK değeri al,
# sınıra dayanan değerleri ALMA.
# ============================================================
FLEX_16_SERVO2_DOWN_VALUE: Optional[float] = None


# ============================================================
# FLEX-17 — SERVO3 GRAPPLE VALUE (kavrama)
#
# WHY FLEXIBLE:
# Kavrama mekanizmasını kapatan normalize actuator değeri (-1..1),
# servo tipine ve kavrama kolunun mekanik strokuna bağlı.
#
# REAL-WORLD TEST NEEDED:
# Bench test: payload takılıyken kavramanın güvenilir tuttuğu, ama
# servonun stall'a girmediği değer ölçülmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# RealPayloadBackend.grapple() (V33: SERVO3_GRAPPLE).
#
# HOW TO CALIBRATE:
# FLEX-16 ile aynı adım adım yöntem; ek olarak kavrama kuvvetini
# payload'ı asarak doğrula (servo akımı stall seviyesine çıkmamalı).
# ============================================================
FLEX_17_SERVO3_GRAPPLE_VALUE: Optional[float] = None


# ============================================================
# FLEX-18 — SERVO2 REVERSE VALUE (geri çekme / toparlama)
#
# WHY FLEXIBLE:
# Kancayı geri çeken normalize actuator değeri (-1..1), FLEX-16 ile
# aynı nedenlerle montaja bağlı.
#
# PAYLAŞIM NOTU (KASITLI):
# retract() (V33: SERVO2_REVERSE, 1. kullanım) ve stow() (V33:
# SERVO2_REVERSE, 2./son kullanım) AYNI fiziksel komuttur -- ikisi de
# bu tek FLEX-18 değerini kullanır. Bunlar kasıtlı olarak iki ayrı
# FLEX'e BÖLÜNMEDİ: fiziksel olarak tek bir servo hedef konumu var,
# iki kopya olsaydı kalibrasyonda birbirinden sapabilirlerdi.
# (Karşılaştır: FLEX-05 "ne kadar" mesafe ve FLEX-13 "ne sürede"
# timeout AYRI tutulmuştur -- onlar farklı fiziksel büyüklükler,
# bu ise aynı büyüklüğün iki kullanımı.)
#
# REAL-WORLD TEST NEEDED:
# Bench test: kancanın tam toplanmış konuma ulaştığı ve mekanik sınıra
# dayanmadığı değer, hem yüklü (retract) hem yüksüz (stow) durumda
# doğrulanmalı.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# RealPayloadBackend.retract() VE RealPayloadBackend.stow().
#
# HOW TO CALIBRATE:
# FLEX-16 ile aynı adım adım yöntem, ters yönde. Yüklü durumda da
# aynı değerin yeterli olduğunu doğrula; yetmiyorsa bu bir tasarım
# bulgusudur ve FLEX-18'in ikiye bölünmesi TARTIŞILMALIDIR (sessizce
# yeni bir sayı eklenmemeli).
# ============================================================
FLEX_18_SERVO2_REVERSE_VALUE: Optional[float] = None


# ============================================================
# FLEX-19 — SERVO3 RELEASE VALUE (bırakma)
#
# WHY FLEXIBLE:
# Kavramayı açan normalize actuator değeri (-1..1), FLEX-17 ile aynı
# nedenlerle mekanizmaya bağlı.
#
# REAL-WORLD TEST NEEDED:
# Bench test: payload'ın takılmadan/sürtünmeden tam serbest kaldığı
# açılma değeri ölçülmeli.
#
# CURRENT DEFAULT:
# TBD — bench test gerekli.
#
# AFFECTS:
# RealPayloadBackend.release() (V33: SERVO3_RELEASE).
#
# HOW TO CALIBRATE:
# FLEX-17 ile aynı yöntem, ters yönde; payload'ın asılı kalmadan
# düştüğünü en az 10 tekrarda doğrula.
# ============================================================
FLEX_19_SERVO3_RELEASE_VALUE: Optional[float] = None


# ============================================================
# FLEX-20 — GAZEBO CAPTURE ENVELOPE
#
# WHY FLEXIBLE:
# Gazebo'da HookAttachSystem'e attach komutu göndermeden önce aracın
# payload'a ne kadar yakın olması gerektiği. Bu bir SİMÜLASYON toleransıdır:
# ne kadar yakınken attach'i "meşru bir yakalama" saydığımız, sim'deki
# model boyutlarına, poz okuma gecikmesine ve alçalma hassasiyetine bağlı.
#
# NEDEN FLEX-01'DEN AYRI BİR NUMARA (KASITLI):
# FLEX-01 bench'te ÖLÇÜLEN gerçek-dünya büyüklüğü: kanca geometrisi,
# manyetik alan menzili ve sensör toleransıyla tanımlı. Gazebo'da NE
# MIKNATIS NE DE KANCA GEOMETRİSİ VAR -- HookAttachSystem base_link'i
# doğrudan payload'ın link'ine "fixed" joint ile kaynaklıyor. İkisi aynı
# birimi paylaşan FARKLI fiziksel büyüklüklerdir. FLEX-01'i burada
# kullanmak, bir bench ölçümünü hiçbir anlamı olmadığı bir bağlama sessizce
# taşımak ve gerçek donanım kalibrasyonunun sim'i doğruladığı yanılsamasını
# yaratmak olurdu.
#
# NEDEN BU KAPI HİÇ GEREKLİ (ÖNEMLİ):
# HookAttachSystem.cc HİÇBİR mesafe/yakınlık kontrolü yapmaz -- 232 satırda
# tek bir Pose/Position component okuması, tek bir norm hesabı yoktur
# (include'lar yalnızca Name, Model, Link, ParentEntity, DetachableJoint).
# Plugin, istenirse payload'ı 1 km öteden de kaynaklar; kendi yorumuna göre
# temas testi ÇAĞIRANA aittir (HookAttachSystem.cc:33-35). Bu kapı olmadan
# GazeboPayloadBackend, araç payload'dan 50 m uzaktayken bile "yakalandı"
# raporlardı.
#
# REAL-WORLD TEST NEEDED:
# Yok -- bu saha ölçümü değil, SITL karakterizasyonu: sim'de araç payload'a
# kademeli olarak yaklaştırılıp, attach komutunun hangi mesafeden itibaren
# fiziksel olarak makul bir yakalamaya karşılık geldiği belirlenmeli.
#
# CURRENT DEFAULT:
# 0.45 m (operatör kararı, 2026-08-24; önceki değerler 0.30 -> 0.35).
#
# REVİZYON 1 (2026-08-23, Phase 6 acceptance ölçümü sonrası):
# 0.30m'den 0.35m'ye yükseltildi -- ölçülen PX4 yer-etkisi hover hatası
# (~3-6cm, production_altitude testinde 0.303-0.311m gözlendi) için marj.
#
# REVİZYON 2 (2026-08-24, Phase 15 tam Task 3 SITL koşusu sonrası):
# 0.35m'den 0.45m'ye yükseltildi. GEREKÇE, ölçümle:
#   * Phase 6 acceptance, üretim irtifasında doğrudan ölçülen açıklıklar:
#     0.291 / 0.303 / 0.307 / 0.311 / 0.325 m.
#   * Phase 15'te 3 uçtan uca koşudan 1'i (koşu B) bu kapıya takıldı --
#     alçalma PX4'te 0.348 m'ye ulaşmıştı (hedef 0.30), ama Gazebo'da
#     base_link zemin üstünde ~0.06 m durduğu için ölçülen açıklık
#     0.35 eşiğini AŞTI. Koşu A ve C geçti.
# Yani ulaşılabilir açıklık bandının üst ucu 0.35'i aşıyor ve eşik tam
# bandın tepesindeydi. 0.45, ölçülen en kötü durumun belirgin üstünde
# ama hâlâ "meşru yakalama" aralığında (0.80 m açıklıkta payload aracın
# 0.83 m altında sarkıyor -- bkz. Phase 6 sarkma gözlemi).
#
# HÂLÂ FİZİKSEL BİR ÖLÇÜM DEĞİL, POLİTİKA EŞİĞİ. Bu revizyon eşiğin
# ulaşılabilir olmasını sağlar; "doğru" değerin ne olduğunu söylemez.
#
# PROVENANCE: Fiziksel ölçümden TÜRETİLEMEDİ (Phase 5.5 Adım D, negatif
# sonuç -- DetachableJoint "fixed" tipi mesafeyle orantılı sinyal
# üretmiyor). Bunun yerine GOREV3_DESCENT_ALTITUDE_M (0.30 m, zaten
# üretimde çalışan bir tasarım sabiti) ile TUTARLI tutuldu -- iki değerin
# bağımsız sürüklenmesini önlemek için. Bu bir POLİTİKA eşiği, fiziksel
# bench ölçümü DEĞİL. Phase 16'da FLEX-01 bench'te karakterize
# edildiğinde, ikisinin (Real/Gazebo envelope semantiği) Phase 15 parity
# testinde tutarlı olup olmadığı YENİDEN gözden geçirilecek.
#
# NOT (repo düzeltmesi): GOREV3_DESCENT_ALTITUDE_M gorev3_pickup.py'de
# TANIMLI DEĞİL, core/config/parameters.py:16'da tanımlı; gorev3_pickup.py
# ve gorev3_redrop.py onu yalnızca import ediyor.
#
# NEYİ KAPILAR -- DİKEY AÇIKLIK (2026-08-23 operatör kararı):
# Bu eşik, araç ile payload arasındaki 3B MERKEZ-MERKEZ mesafeyle DEĞİL,
# DİKEY AÇIKLIKLA karşılaştırılır: vehicle_z - (payload_z + payload
# yarı-yüksekliği). Gerekçe ölçümle sabit: Adım D'de araç üretim
# irtifasındayken (0.339 m) merkez-merkez mesafe 0.317 m çıktı, yani
# 0.30 eşiğinin ÜSTÜNDE -- o semantikle kapı üretim irtifasında HİÇ
# açılmazdı ve alçalmak da çözmüyordu (0.15 hedefinde yatay sapma 0.292 m
# olup 3B mesafeyi 0.343'e ÇIKARDI). Kök neden bir değer hatası değil,
# semantik uyumsuzluktu: "irtifa AGL" ile "merkez-merkez ayrım" aynı
# fiziksel büyüklük değildir (arada payload'ın yarı-yüksekliği + hover
# tutma hatası vardır). Dikey açıklık semantiğiyle aynı ölçümde değer
# 0.289 m'dir ve kapı açılır.
#
# AFFECTS:
# GazeboPayloadBackend.is_in_capture_zone() ve GazeboPayloadBackend.deploy()
# -- deploy() bu kapıdan geçmeden /hook/attach YAYINLAMAZ. CALIBRATION
# GUARD: bu değer None iken ikisi de PayloadCalibrationError ile durur ve
# simülasyona hiçbir mesaj gitmez. Açıklığın TEK formülü
# gz_system/gz_hook_client.py::_vertical_clearance()'tir.
#
# TODO(PHASE-15-PARITY): Gazebo'da retract()/stow() no-op olduğu
# için (joint 'fixed', re-pozisyonlama yok) payload, yakalandığı
# açıklıkta SONSUZA KADAR sarkık kalıyor -- retract sonrası
# "güvenceye alınmış/yaslanmış" pozisyon Gazebo'da TEMSİL
# EDİLEMİYOR. Phase 6 ölçümü: 0.30m açıklıkta payload aracın
# 0.41m altında asılı, tüm transport boyunca böyle kalıyor. Bu,
# FLEX-20'nin yanlış olduğu anlamına gelmez -- Gazebo'nun
# "capture" ile "secured" arasındaki gerçek dünya ayrımını
# temsil edemediği anlamına gelir. Phase 15 parity testinde Real
# backend'in FLEX-01+retract davranışıyla karşılaştırılırken bu
# fark ele alınmalı; muhtemel çözüm retract() çağrıldığında
# joint'i yeniden konumlandırmak (Gazebo backend'e yeni iş),
# config değeri değişikliği DEĞİL.
#
# HOW TO CALIBRATE:
# Bu değer ölçümle türetilemez (yukarıdaki PROVENANCE'a bkz.) -- politika
# olarak seçilir. Gözden geçirirken sorulacak soru "hangi mesafede attach
# çalışıyor" DEĞİLDİR (hepsinde çalışır; HookAttachSystem mesafe kontrolü
# yapmaz), "hangi açıklığı meşru bir yakalama saymak istiyoruz"dur.
# Veri için: tools/calibrate_flex20_gazebo.py hem 3B mesafeyi hem dikey
# açıklığı loglar; ayrıca Phase 6 acceptance koşusu farklı açıklıklarda
# payload'ın kancadan ne kadar sarktığını raporlar.
# ============================================================
FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M: Optional[float] = 0.45


# ============================================================
# FLEX-21 — HOOK MOUNT OFFSET (kamera merkezi -> kanca), BODY FRAME
#
# WHY FLEXIBLE:
# Kameranın gördüğü nokta ile kancanın fiziksel olarak indiği nokta aynı
# değildir: kamera ve kanca gövdeye farklı yerlerden monteli. Vision
# payload'ı kare merkezine getirdiğinde araç kamerayı hedefe hizalamış
# olur, KANCAYI değil. Aradaki montaj kolu telafi edilmezse kanca,
# payload'ın yanına iner.
#
# NEDEN FLEX-09'DAN AYRI BİR NUMARA (KASITLI):
# FLEX-09 "HOOK-TO-PAYLOAD ALIGNMENT OFFSET" olarak tanımlı ve AFFECTS'i
# is_in_capture_zone() -- yani KANCA ile PAYLOAD arasındaki mesafe, payload
# tarafı bir büyüklük. FLEX-21 ise KAMERA ile KANCA arasındaki montaj kolu,
# vision tarafı bir büyüklük. İkisi farklı fiziksel gerçekliktir ve ayrı
# ölçülür; aynı numarayı paylaşmaları, tek bir kalibrasyon değerinin iki
# farklı ölçümü temsil etmesi anlamına gelirdi.
#
# ÇERÇEVE VE BOYUT (2026-08-23 operatör kararı):
# 2 bileşen, (forward_m, right_m), PX4 BODY (FRD) çerçevesinde -- repodaki
# iki emsaliyle birebir aynı konvansiyon:
#   core/config/parameters.py::CAMERA_LEVER_ARM_BODY_M   = (0.35, 0.0)
#   core/config/parameters.py::PAYLOAD_MOUNT_OFFSET_BODY_M
# Z bileşeni KASITLI olarak YOK: alçalma irtifası ayrıca komut ediliyor,
# dikey bir bileşenin tüketicisi olmazdı ve ölü alan yanlış kullanıma
# davetiye çıkarırdı. Çerçeve konvansiyonuna sadık kalmak ucuz değil ama
# gerekli: gz_payload_actuator.py::measure_mount_vector() docstring'i,
# Gazebo FLU ile PX4 FRD karıştırıldığı için İKİ uçuşun kaybedildiğini
# belgeliyor.
#
# REAL-WORLD TEST NEEDED:
# Fiziksel/CAD ölçüm: kamera optik merkezinin izdüşümü ile kancanın
# indiği nokta arasındaki ileri/sağ mesafe. CAMERA_LEVER_ARM_BODY_M ile
# aynı yöntem (o değer dört uçuşta doğrulandı: tahmin 0.25 m sapma,
# ölçüm 0.252/0.264/0.290/0.305 m).
#
# CURRENT DEFAULT:
# TBD -- None. Tahmin EDİLMEDİ.
#
# None'IN ANLAMI (KASITLI, "sessizce sıfır varsayma" DEĞİL):
# Burada None "bilinmeyen bir sayı" değil, "henüz ölçülmüş bir DÜZELTME
# yok" demektir. Düzeltmesiz halin güvenli karşılığı öteleme YAPMAMAKtır --
# ve bu, bu FLEX eklenmeden önceki davranışın ta kendisidir. Bu yüzden
# None iken hiçbir öteleme uygulanmaz ve akış bugünküyle BİREBİR aynı
# kalır (bkz. gorev3_pickup.py::_center_over_payload, Görev 2'nin
# payload_release.py:98 `if mount:` deseniyle aynı). Kalibre edilmemiş
# olması bir kez loglanır, sessiz kalmaz.
#
# AFFECTS:
# core/mission/gorev3_pickup.py::_center_over_payload() -- TEK uygulama
# noktası. Ofset oradan CenteringController.descend_to_release()'e
# geçirilir ve dondurulmuş hedef kestiriminin saf ötelemesi olarak BİR KEZ
# uygulanır (body->NED, yaw ile, sonra çıkarılır).
#
# NEDEN MERKEZLEME DÖNGÜSÜNE BIAS OLARAK VERİLMEZ:
# centering_controller.py::descend_to_release() docstring'i ölçümle
# yasaklıyor: "This replaces biasing the vision error (the first A2), which
# corrupted the measurement it depended on and produced no net improvement:
# 40.1 / 32.5 cm against a 33.7-37.3 cm baseline." Ofset merkezleme
# yakınsadıktan SONRA, tek seferde uygulanır.
#
# HOW TO CALIBRATE:
# Aracı bilinen bir işaretin üstünde merkezleyip kancayı indir; kancanın
# indiği nokta ile işaret arasındaki ileri/sağ farkı ölç. En az 5 tekrar,
# ortalama al. İşaretin görüntüdeki merkezi ile kancanın yere değdiği
# nokta arasındaki fark, aranan vektördür.
# ============================================================
FLEX_21_HOOK_MOUNT_OFFSET_BODY_M: Optional[Tuple[float, float]] = None
