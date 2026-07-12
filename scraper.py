import os
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from urllib.parse import urljoin

def scrape_author_articles():
    print("--- Web Makale Toplayıcıya Hoş Geldiniz ---")
    
    # Kullanıcı Inputları
    base_url = input("Web sitesinin ana linkini girin (örn: https://medium.com): ").strip()
    author_name = input("Yazar adını girin: ").strip()
    output_dir = input("Dosyaların kaydedileceği klasör yolu (örn: ./makaleler): ").strip()

    # Klasör oluşturma
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Klasör oluşturuldu: {output_dir}")

    try:
        # 1. Aşama: Siteyi tarayıp yazarın makale linklerini bulma
        print(f"\n{base_url} adresi taranıyor...")
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Yazar adını içeren tüm linkleri ara (Genel yaklaşım)
        links = []
        for a in soup.find_all("a", href=True):
            if author_name.lower() in a.text.lower():
                full_url = urljoin(base_url, a["href"])
                if full_url not in links:
                    links.append(full_url)

        if not links:
            print("Belirtilen yazarla ilgili herhangi bir link bulunamadı.")
            return

        print(f"{len(links)} adet potansiyel makale linki bulundu. İşleniyor...")

        # 2. Aşama: Her bir linke gidip içeriği çekme ve MDye dönüştürme
        for i, link in enumerate(links, 1):
            try:
                print(f"[{i}/{len(links)}] Çekiliyor: {link}")
                art_res = requests.get(link, timeout=10)
                art_res.raise_for_status()
                art_soup = BeautifulSoup(art_res.text, "html.parser")

                # Makale başlığını bulmaya çalış
                title = art_soup.find("h1")
                title_text = title.text.strip() if title else f"makale_{i}"
                # Dosya adını temizle (geçersiz karakterleri kaldır)
                safe_title = "".join([c for c in title_text if c.isalnum() or c in (" ", "_", "-")]).rstrip()
                filename = f"{safe_title}.md"

                # Makale içeriğini bulmaya çalış ( Yaygın makale kapsayıcıları: article, main, div.content vb.)
                content_area = art_soup.find("article") or art_soup.find("main") or art_soup.find("div", class_="content")
                
                if content_area:
                    html_content = str(content_area)
                else:
                    # Eğer özel bir alan bulunamazsa bodynin tamamını al
                    html_content = str(art_soup.body)

                # HTML -> Markdown Dönüşümü
                markdown_text = md(html_content, heading_style="ATX")
                
                # Dosyayı kaydet
                file_path = os.path.join(output_dir, filename)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"# {title_text}\n\nKaynak: {link}\n\n---\n\n{markdown_text}")
                
                print(f"✅ Kaydedildi: {filename}")

            except Exception as e:
                print(f"❌ {link} içeriği alınırken hata oluştu: {e}")

        print(f"\nİşlem tamamlandı! Tüm dosyalar {output_dir} klasörüne kaydedildi.")

    except requests.exceptions.RequestException as e:
        print(f"Kritik Hata: Siteye erişilemedi. {e}")

if __name__ == "__main__":
    scrape_author_articles()
