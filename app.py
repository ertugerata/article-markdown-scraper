import os
import requests
import zipfile
from flask import Flask, render_template, request, send_file, flash
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from urllib.parse import urljoin
from io import BytesIO

app = Flask(__name__)
app.secret_key = "hermes_secret_key"

# HTML Template'i kodun içinde tanımlıyorum (Ayrı bir dosya ile uğraşmamanız için)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Makale Toplayıcı</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; padding-top: 50px; }
        .container { max-width: 600px; background: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 30px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>📚 Makale Toplayıcı</h2>
            <p class="text-muted">Yazar adına göre makaleleri Markdown olarak indir</p>
        </div>
        
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for message in messages %}
              <div class="alert alert-info">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form method="POST" action="/scrape">
            <div class="mb-3">
                <label class="form-label">Web Sitesi URL</label>
                <input type="url" name="base_url" class="form-control" placeholder="https://example.com" required>
            </div>
            <div class="mb-3">
                <label class="form-label">Yazar Adı</label>
                <input type="text" name="author_name" class="form-control" placeholder="Yazarın tam adı" required>
            </div>
            <button type="submit" class="btn btn-primary w-100">Makaleleri Çek ve İndir (.zip)</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/scrape', methods=['POST'])
def scrape():
    base_url = request.form.get('base_url').strip()
    author_name = request.form.get('author_name').strip()

    try:
        # 1. Aşama: Linkleri Bulma
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        links = []
        for a in soup.find_all('a', href=True):
            if author_name.lower() in a.text.lower():
                full_url = urljoin(base_url, a['href'])
                if full_url not in links:
                    links.append(full_url)

        if not links:
            flash("Belirtilen yazarla ilgili makale bulunamadı.")
            return render_template_string(HTML_TEMPLATE)

        # 2. Aşama: İçerikleri Çekme ve Bellekte Zip'leme
        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, link in enumerate(links, 1):
                try:
                    art_res = requests.get(link, timeout=10)
                    art_res.raise_for_status()
                    art_soup = BeautifulSoup(art_res.text, 'html.parser')

                    title = art_soup.find('h1')
                    title_text = title.text.strip() if title else f"makale_{i}"
                    safe_title = "".join([c for c in title_text if c.isalnum() or c in (' ', '_', '-')]).rstrip()
                    
                    content_area = art_soup.find('article') or art_soup.find('main') or art_soup.find('div', class_='content')
                    html_content = str(content_area) if content_area else str(art_soup.body)
                    
                    markdown_text = md(html_content, heading_style="ATX")
                    final_content = f"# {title_text}\n\nKaynak: {link}\n\n---\n\n{markdown_text}"
                    
                    # Zip içine dosyayı ekle
                    zf.writestr(f"{safe_title}.md", final_content)
                except Exception:
                    continue

        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{author_name}_makaleler.zip"
        )

    except Exception as e:
        flash(f"Bir hata oluştu: {str(e)}")
        return render_template_string(HTML_TEMPLATE)

# Helper for internal template rendering
from flask import render_template_string
if __name__ == "__main__":
    app.run(debug=True, port=5000)
