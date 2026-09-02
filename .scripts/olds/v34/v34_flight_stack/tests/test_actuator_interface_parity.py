"""IPayloadActuator implementasyonlari arayuzle ve GERCEK CAGRI YERLERIYLE uyumlu mu.

Denetim bulgusu B2'den (2026-09-02) geliyor. RealPayloadActuator.
activate_pickup_mechanism `(self)` idi; core/mission/gorev3_pickup.py:906 ise
`activate_pickup_mechanism(altitude_m=..., on_retry=...)` diye cagiriyordu.
Sonuc: gercek ucusta Gorev 3 Faz 1 servo tetikleme aninda TypeError.

Bu sinifta hata SIMULASYONDA GORUNMEZ, cunku orada GzPayloadActuator
kullaniliyor ve onun imzasi dogruydu -- yani hicbir SITL kosumu bunu
yakalayamazdi. Bu yuzden imza paritesi ayrica pinleniyor.
"""
import inspect

import pytest

from core.interfaces.i_payload_actuator import IPayloadActuator
from gz_system.gz_payload_actuator import GzPayloadActuator
from mocks.mock_payload_actuator import MockPayloadActuator
from real_system.real_payload_actuator import RealPayloadActuator

IMPLEMENTATIONS = [GzPayloadActuator, RealPayloadActuator, MockPayloadActuator]
ABSTRACT_METHODS = [
    "release_payload_at_mavi_altigen",
    "release_payload_at_kirmizi_ucgen",
    "activate_pickup_mechanism",
    "activate_drop_mechanism",
]

#: Uretimin GERCEKTEN kullandigi cagri sekli. Kaynak:
#: core/mission/gorev3_pickup.py:906-907.
PRODUCTION_CALLS = {
    "activate_pickup_mechanism": ((), {"altitude_m": 1.2, "on_retry": lambda: None}),
    "release_payload_at_mavi_altigen": ((), {}),
    "release_payload_at_kirmizi_ucgen": ((), {}),
    "activate_drop_mechanism": ((), {}),
}


@pytest.mark.parametrize("impl", IMPLEMENTATIONS, ids=lambda c: c.__name__)
@pytest.mark.parametrize("method_name", ABSTRACT_METHODS)
def test_implementation_accepts_the_production_call(impl, method_name):
    """Her implementasyon, uretimin o metodu cagirdigi SEKILDE cagrilabilmeli.

    inspect.Signature.bind() tam olarak Python'un cagri aninda yapacagi
    eslestirmeyi yapar -- yani bu test B2'yi araci ucurmadan yakalar."""
    method = getattr(impl, method_name)
    args, kwargs = PRODUCTION_CALLS[method_name]
    try:
        inspect.signature(method).bind(impl, *args, **kwargs)
    except TypeError as e:
        pytest.fail(f"{impl.__name__}.{method_name} uretim cagrisini kabul etmiyor: {e}")


@pytest.mark.parametrize("impl", IMPLEMENTATIONS, ids=lambda c: c.__name__)
@pytest.mark.parametrize("method_name", ABSTRACT_METHODS)
def test_implementation_is_signature_compatible_with_the_interface(impl, method_name):
    """Arayuzun kabul ettigi HER cagri, implementasyonda da kabul edilmeli.

    Implementasyon EK opsiyonel parametre tanimlayabilir (GzPayloadActuator
    deck_height_m'e varsayilan veriyor); yasak olan, arayuzun vaat ettigi bir
    parametreyi KABUL ETMEMEK."""
    interface_params = inspect.signature(getattr(IPayloadActuator, method_name)).parameters
    impl_sig = inspect.signature(getattr(impl, method_name))
    optional = {name for name, p in interface_params.items()
                if name != "self" and p.default is not inspect.Parameter.empty}
    try:
        impl_sig.bind(impl, **{name: None for name in optional})
    except TypeError as e:
        pytest.fail(f"{impl.__name__}.{method_name} arayuzun opsiyonel "
                    f"parametrelerini ({sorted(optional)}) kabul etmiyor: {e}")


@pytest.mark.parametrize("impl", IMPLEMENTATIONS, ids=lambda c: c.__name__)
def test_implementation_is_instantiable(impl):
    """Soyut bir metot eksik kalirsa sinif instantiate EDILEMEZ -- bu, tum
    entrypoint'i toplama asamasinda dusuren sessiz bir hatadir."""
    missing = getattr(impl, "__abstractmethods__", frozenset())
    assert not missing, f"{impl.__name__} soyut metotlari implemente etmemis: {sorted(missing)}"
