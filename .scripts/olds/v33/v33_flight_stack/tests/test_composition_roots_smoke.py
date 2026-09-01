"""Composition root'larin ADLARININ ve IMPORTLARININ tutarliligi.

NEDEN VAR (2026-08-24 bulgusu): dinamik sira degisikliginde main_gz.py'ye
PAYLOAD_MODEL_BY_SHAPE kullanimi eklendi ama IMPORT'u eklenmedi. Modul
import edilebiliyordu (hata _run() icinde, calisma aninda tetikleniyordu),
bu yuzden 600 testin HICBIRI yakalamadi -- yalnizca SITL kosusu patladi.

Bu dosya o boslugu kapatir: her root'un modul govdesinde adi gecen her
sembolun gercekten cozulebildigini dogrular.
"""
import ast
import importlib
import io

import pytest

ROOTS = ["gz_system.main_gz", "real_system.main_real", "dual_system.main_dual"]


@pytest.mark.parametrize("module_name", ROOTS)
def test_root_imports_cleanly(module_name):
    importlib.import_module(module_name)


@pytest.mark.parametrize("module_name", ROOTS)
def test_every_global_name_used_in_root_resolves(module_name):
    """Modulde kullanilan her UST-SEVIYE isim ya import edilmis, ya modulde
    tanimli, ya da builtin olmali. Calisma aninda NameError patlamasin."""
    module = importlib.import_module(module_name)
    source = io.open(module.__file__, encoding="utf-8").read()
    tree = ast.parse(source)

    # Fonksiyon govdelerindeki yerel adlari dislamak icin: yalnizca modulde
    # cozulmesi gereken, BUYUK HARFLI sabit benzeri adlari kontrol et.
    used = {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
            and n.id.isupper() and len(n.id) > 3}
    assigned = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}

    missing = sorted(name for name in used
                     if not hasattr(module, name) and name not in assigned)
    assert not missing, f"{module_name}: cozulemeyen sabit(ler): {missing}"
