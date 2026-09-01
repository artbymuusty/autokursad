"""
DEPRECATED (PHASE 6.5, 2026-08-23)
==================================
Bu dosya payload/ paketi tarafindan supersede edildi (bkz. Phase 4/6.5
karari). Yeni kod buradan CAGIRMASIN. Kaldirma karari ayri, bu fazin
kapsaminda DEGIL.

Gorev 3'un alma/birakma yolu (activate_pickup_mechanism /
activate_drop_mechanism) artik payload/PayloadManager uzerinden gidiyor
(gorev3_pickup.py, gorev3_redrop.py). Gorev 2'nin iki birakma metodu
(release_payload_at_*) HALA bu arayuzden cagriliyor -- supersede bu fazda
KISMIdir; Gorev 2 tarafi ayri bir fazin konusu.

BU DOSYA, PROJEDE GERÇEK DONANIM KOMUTUNUN YAZILACAĞI TEK YERDİR. core/ ve gz_system/
içinde bu tarz TODO veya donanım-özel kod OLMAMALIDIR. Fiziksel testler tamamlandığında
yalnızca bu dosyadaki dört metod güncellenecektir; core/ ve gz_system/ değişmeyecektir.
"""

import asyncio
import logging
from core.interfaces.i_payload_actuator import IPayloadActuator

logger = logging.getLogger(__name__)

class RealPayloadActuator(IPayloadActuator):
    
    async def release_payload_at_mavi_altigen(self) -> bool:
        """Görev 2 Rapor Bölüm 12: servo 90° sağa, ardından 90° sola hareket ederek
        Mavi Altıgen'deki yükü bırakır."""
        logger.info("release_payload_at_mavi_altigen cagrildi")
        # FIRST MISSION SERVO
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        # Beklenen davranış: servo 90° sağa, ardından 90° sola (Görev 2 Rapor Bölüm 12).
        # Önerilen kütüphane: pigpio / RPi.GPIO / PX4 AUX kanalı (MAVSDK Actuator Control).
        # Bağlantı noktası (pin/kanal) real_system/config/real_system.yaml içinde tanımlanacak.
        await asyncio.sleep(0.5)  # simüle gecikme, gerçek servo süresiyle değiştirilecek
        logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
        return True

    async def release_payload_at_kirmizi_ucgen(self) -> bool:
        """Görev 2 Rapor Bölüm 12: İkinci yük bırakma mekanizması."""
        logger.info("release_payload_at_kirmizi_ucgen cagrildi")
        # SECOND MISSION SERVO
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        await asyncio.sleep(0.5)
        logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
        return True
        
    async def activate_pickup_mechanism(self) -> bool:
        """Görev 3 Rapor Bölüm 5, Adım 6: Yük alma mekanizmasını aktifleştirir."""
        logger.info("activate_pickup_mechanism cagrildi")
        # THIRD MISSION SERVO
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        await asyncio.sleep(0.5)
        logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
        return True

    async def activate_drop_mechanism(self) -> bool:
        """Görev 3 Rapor Bölüm 7, Adım 5: Taşınan yükü bırakır."""
        logger.info("activate_drop_mechanism cagrildi")
        # GRAB SERVO
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        await asyncio.sleep(0.5)
        logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
        return True
