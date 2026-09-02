# Proje Kuralları — KESİN UYULACAK

## GitHub / Push Kuralı
Açık izin olmadan hiçbir push işlemi yapma:
- `git push`, `git push --force`, `--force-with-lease` çalıştırma
- Otomatik deployment veya remote'a veri gönderme başlatma
- Commit yapmak = push izni DEĞİLDİR
- "Kaydet", "commit yap", "tamamla", "uygula" push izni DEĞİLDİR
- Yalnızca "pushla" / "GitHub'a gönder" gibi açık komut push izni sayılır
- Emin değilsen PUSH YAPMA

## İnternet / İndirme Kuralı
Şu komutlardan biri gerekiyorsa ÖNCE dur, rapor ver, onay bekle:
git clone/pull, npm/pnpm/yarn install veya ci, pip install, brew install,
cargo/go dependency indirme, docker pull, SDK/model/büyük dosya indirme,
network'ten veri çeken herhangi bir script.

Rapor formatı:
İNTERNET KULLANIM RAPORU
- Yapılacak işlem:
- İndirilecek dosya/paketler:
- Tahmini boyut:
- Tahmini tüketim:
- Neden gerekli:
- Zorunlu mu / alternatif var mı:

Küçük/zorunlu network işlemlerini gereksiz yere engelleme, ama tahmini
maliyeti belirt. Emin değilsen DUR VE SOR.
