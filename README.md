# Makale Toplayıcı (Article Scraper)

Bu uygulama, belirli bir web sitesinden seçilen bir yazara ait tüm makaleleri otomatik olarak bulan ve bunları Markdown (.md) formatında indirmenizi sağlayan bir web aracıdır.

## 🚀 Özellikler
- **Yazar Bazlı Filtreleme:** Sitedeki linkleri tarayarak sadece ilgili yazara ait içerikleri toplar.
- **Markdown Dönüşümü:** HTML içeriği, temiz ve okunabilir Markdown formatına dönüştürür.
- **Web Arayüzü:** Flask ile geliştirilmiş, kolay kullanımlı modern bir arayüz.
- **Zip Arşivi:** Toplanan tüm makaleler tek bir `.zip` dosyası olarak indirilebilir.

## 🛠️ Kurulum ve Çalıştırma

### 1. Gereksinimleri Yükleyin
```bash
pip install -r requirements.txt
```

### 2. Uygulamayı Başlatın
```bash
python app.py
```

### 3. Kullanım
Tarayıcınızdan `http://127.0.0.1:5000` adresine gidin, site linkini ve yazar adını girerek makaleleri indirin.
