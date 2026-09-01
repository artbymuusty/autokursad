"""PHASE 5 (ADIM 0): payload/ paketinin paylaşılan exception tipleri.

Bu modül PHASE 5'te, PayloadCalibrationError'ın Real ve Gazebo
backend'lerinin ORTAK hata tipi olması gerektiği netleşince oluşturuldu.
Sınıf PHASE 4'te real_payload_backend.py içinde tanımlanmıştı (oradaki
TODO(PHASE-5) notu tam da bu taşımayı öngörüyordu); davranışı DEĞİŞMEDİ,
sadece konumu değişti.

Neden ayrı bir modül (payload_config.py veya payload_types.py değil):
  * payload_config.py kendi docstring'inde "HER esnek fiziksel
    parametrenin tek kaynağı" olarak tanımlı -- bir registry; exception
    sınıfı bir parametre değildir.
  * payload_types.py "PayloadManager'ın public API'sinin ve state
    machine'inin üzerine kurulduğu paylaşılan sözlük" -- PayloadState ve
    PayloadResult oraya aittir; kalibrasyon hatası ise API sözlüğünün
    değil, backend uygulama katmanının bir kavramıdır.
  * Bir backend'in diğerinden import etmesi (gazebo -> real) mimari
    olarak yanlış olurdu: iki backend birbirinden habersiz olmalı.
"""


class PayloadCalibrationError(RuntimeError):
    """CALIBRATION GUARD: kalibre edilmemiş (TBD/None) bir FLEX parametresi
    ile gerçek bir donanım/simülasyon komutu gönderilmeye çalışıldı.

    Bu, payload_config.py'nin "hiçbir sayı tahmin edilmez" kuralının
    çalışma zamanındaki karşılığıdır: None bir actuator index'i, değeri
    veya mesafesi, sessizce 0'a dönüşüp yanlış komutu üretmek yerine
    burada gürültülü şekilde durur. Guard her zaman ilgili RPC/servis
    çağrısından ÖNCE çalışır -- yani kalibre edilmemiş bir sistemde
    donanıma (veya simülasyona) hiçbir komut gitmez.

    Real ve Gazebo backend'leri bu TEK tipi paylaşır: üst katman
    "kalibrasyon eksik" durumunu hangi backend'in bağlı olduğunu bilmeden
    yakalayabilmelidir.
    """
