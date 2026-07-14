import os
import requests
import concurrent.futures
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from flask import Flask, render_template_string, request, Response, jsonify

app = Flask(__name__)
app.secret_key = "hermes_secret_key"

def clean_url(url):
    return url.split('#')[0].split('?')[0].strip()

def get_domain(url):
    return urlparse(url).netloc

def is_valid_article_link(url, base_domain):
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != base_domain:
        return False

    path = parsed.path.lower()
    # Exclude common non-article paths
    exclude_patterns = [
        r'/tag/', r'/category/', r'/categories/', r'/author/', r'/user/',
        r'/page/', r'/search', r'/about', r'/contact', r'/privacy',
        r'/terms', r'/wp-json', r'/xmlrpc', r'/wp-admin', r'/login',
        r'/signup', r'/register', r'/cart', r'/checkout', r'/rss', r'/feed'
    ]
    for pattern in exclude_patterns:
        if re.search(pattern, path):
            return False

    # Exclude static assets
    if any(path.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.mp4', '.mp3', '.css', '.js']):
        return False

    return True

def extract_article_links(soup, base_url):
    domain = get_domain(base_url)
    discovered_links = []

    # Let's search inside elements that look like article listings
    containers = soup.find_all(['article', 'main'])
    for cl in ['post', 'entry', 'card', 'article', 'item', 'blog-post', 'story']:
        containers.extend(soup.find_all(class_=re.compile(cl, re.I)))

    if containers:
        for container in containers:
            for a in container.find_all('a', href=True):
                href = clean_url(urljoin(base_url, a['href']))
                if is_valid_article_link(href, domain) and href != clean_url(base_url):
                    if href not in discovered_links:
                        discovered_links.append(href)

    # If we didn't find enough or any links this way, let's look at any link containing header tags
    for h in soup.find_all(['h1', 'h2', 'h3', 'h4']):
        a_parent = h.find_parent('a', href=True)
        if a_parent:
            href = clean_url(urljoin(base_url, a_parent['href']))
            if is_valid_article_link(href, domain) and href != clean_url(base_url):
                if href not in discovered_links:
                    discovered_links.append(href)
        else:
            for a in h.find_all('a', href=True):
                href = clean_url(urljoin(base_url, a['href']))
                if is_valid_article_link(href, domain) and href != clean_url(base_url):
                    if href not in discovered_links:
                        discovered_links.append(href)

    # Fallback: check all links on the page that meet the criteria
    if len(discovered_links) < 3:
        for a in soup.find_all('a', href=True):
            href = clean_url(urljoin(base_url, a['href']))
            if is_valid_article_link(href, domain) and href != clean_url(base_url):
                # Ensure the link has some descriptive text
                if len(a.text.strip()) > 15:
                    if href not in discovered_links:
                        discovered_links.append(href)

    return discovered_links

def find_author_articles(base_url, author_name):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        res = requests.get(base_url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching base URL: {e}")
        return []

    domain = get_domain(base_url)
    all_article_links = set()

    # Case 1: Find links whose text matches the author name (author profile links)
    author_profile_urls = []
    for a in soup.find_all('a', href=True):
        if author_name.lower() in a.text.lower():
            full_url = clean_url(urljoin(base_url, a['href']))
            if is_valid_article_link(full_url, domain) or any(keyword in full_url.lower() for keyword in ['author', 'yazar', 'user', 'profile', 'writer']):
                if full_url not in author_profile_urls and full_url != clean_url(base_url):
                    author_profile_urls.append(full_url)

    # Fetch article links from author profiles concurrently
    if author_profile_urls:
        def fetch_profile_links(profile_url):
            try:
                p_res = requests.get(profile_url, headers=headers, timeout=10)
                p_res.raise_for_status()
                p_soup = BeautifulSoup(p_res.text, 'html.parser')
                return extract_article_links(p_soup, profile_url)
            except Exception:
                return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(fetch_profile_links, author_profile_urls)
            for links in results:
                for link in links:
                    all_article_links.add(link)

    # Case 2: Find articles directly on the current page that contain the author's name in their block
    author_blocks = []
    for element in soup.find_all(string=re.compile(re.escape(author_name), re.I)):
        parent = element.parent
        for _ in range(5):
            if parent is None:
                break
            if parent.name in ['article', 'div', 'section', 'li', 'tr'] and parent not in author_blocks:
                if len(parent.text) < 15000:
                    author_blocks.append(parent)
                    break
            parent = parent.parent

    for block in author_blocks:
        for a in block.find_all('a', href=True):
            href = clean_url(urljoin(base_url, a['href']))
            if is_valid_article_link(href, domain) and href != clean_url(base_url):
                all_article_links.add(href)

    # Case 3: If still no links, or if the page itself might be the author profile page
    is_direct_author_page = (
        any(k in base_url.lower() for k in ['author', 'yazar', 'user', 'profile', 'writer']) or
        author_name.lower() in base_url.lower() or
        (soup.title and author_name.lower() in soup.title.text.lower())
    )

    if not all_article_links or is_direct_author_page:
        direct_links = extract_article_links(soup, base_url)
        for link in direct_links:
            all_article_links.add(link)

    return sorted(list(all_article_links))

def extract_title(soup):
    meta_og = soup.find('meta', property='og:title')
    if meta_og and meta_og.get('content'):
        return meta_og['content'].strip()

    h1 = soup.find('h1')
    if h1:
        return h1.text.strip()

    title_tag = soup.find('title')
    if title_tag:
        t_text = title_tag.text.strip()
        for sep in [' - ', ' | ', ' » ', ' : ']:
            if sep in t_text:
                t_text = t_text.split(sep)[0].strip()
        return t_text

    return "Başlıksız Makale"

def extract_date(soup):
    meta_properties = [
        ('property', 'article:published_time'),
        ('name', 'pubdate'),
        ('name', 'publish-date'),
        ('name', 'date'),
        ('name', 'dcterms.date'),
        ('property', 'og:pubdate'),
        ('property', 'og:published_time'),
        ('itemprop', 'datePublished'),
        ('name', 'rdate')
    ]
    for attr, name in meta_properties:
        meta = soup.find('meta', {attr: name})
        if meta and meta.get('content'):
            val = meta['content'].strip()
            if len(val) >= 10 and val[4] == '-' and val[7] == '-':
                return val[:10]
            return val

    time_tag = soup.find('time')
    if time_tag:
        if time_tag.get('datetime'):
            val = time_tag['datetime'].strip()
            if len(val) >= 10 and val[4] == '-' and val[7] == '-':
                return val[:10]
            return val
        if time_tag.text:
            return time_tag.text.strip()

    date_indicators = [
        ('class', 'date'), ('class', 'post-date'), ('class', 'entry-date'),
        ('class', 'published'), ('class', 'time'), ('class', 'datetime'),
        ('class', 'post-meta'), ('class', 'meta'), ('id', 'date'),
        ('class', 'article-date'), ('class', 'article-time'), ('class', 'story-date')
    ]
    for attr, name in date_indicators:
        elements = soup.find_all(lambda tag: tag.has_attr(attr) and any(name in val for val in tag.get(attr) if isinstance(val, str)))
        for el in elements:
            txt = el.text.strip()
            if txt and len(txt) < 50 and any(c.isdigit() for c in txt):
                for prefix in ["yayınlanma tarihi:", "yayınlanma:", "tarih:", "tarihi:", "date:", "published on:", "published:"]:
                    if txt.lower().startswith(prefix):
                        txt = txt[len(prefix):].strip()
                return txt

    return "Belirtilmemiş"

def extract_clean_content(soup):
    unwanted_selectors = [
        'nav', 'header', 'footer', 'aside', 'form', 'iframe', 'script', 'style',
        '.comments', '#comments', '.comment-list', '.comment-form', '.comments-area',
        '.sidebar', '#sidebar', '.aside', '.widget', '#widgets',
        '.share', '.sharing', '.social', '.social-share', '.share-buttons',
        '.advertisement', '.ads', '.ad-box', '.promo', '.adsbygoogle',
        '.related', '.related-posts', '.related-articles',
        '.author-bio', '.author-box', '.about-author',
        '.navigation', '.pagination', '.nav-links',
        '.menu', '.header-menu', '.footer-menu',
        'noscript', 'svg'
    ]

    for selector in unwanted_selectors:
        for element in soup.select(selector):
            element.decompose()

    content_container = None
    container_selectors = [
        'article', 'main', '[role="main"]',
        '.post-content', '.entry-content', '.article-content', '.story-content',
        '.post-body', '.entry-body', '.article-body', '.content', '#content',
        '.main-content', '#main-content', '.main', '#main'
    ]

    for selector in container_selectors:
        container = soup.select_one(selector)
        if container:
            if len(container.text.strip()) > 100:
                content_container = container
                break

    if not content_container:
        content_container = soup.body

    if not content_container:
        content_container = soup

    for el in content_container.find_all(['script', 'style', 'nav', 'footer', 'form', 'iframe', 'noscript', 'aside']):
        el.decompose()

    html_str = str(content_container)
    markdown_text = md(html_str, heading_style="ATX")

    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)

    return markdown_text.strip()

def fetch_article_metadata(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        title = extract_title(soup)
        date = extract_date(soup)
        return {
            'url': url,
            'title': title,
            'date': date,
            'success': True
        }
    except Exception as e:
        return {
            'url': url,
            'title': url,
            'date': 'Hata',
            'success': False
        }

def get_articles_metadata(urls):
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(fetch_article_metadata, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            data = future.result()
            if data['success']:
                results.append(data)
    return results

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Makale Toplayıcı</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #f0f2f5; padding-top: 50px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
        .container { max-width: 800px; background: white; padding: 35px; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); }
        .header { text-align: center; margin-bottom: 35px; }
        .header h2 { font-weight: 700; color: #1a1a1a; }
        .btn-primary { background-color: #4f46e5; border-color: #4f46e5; font-weight: 500; }
        .btn-primary:hover { background-color: #4338ca; border-color: #4338ca; }
        .table-responsive { margin-top: 30px; border-radius: 12px; overflow: hidden; border: 1px solid #e5e7eb; }
        .table { margin-bottom: 0; }
        .table th { background-color: #f9fafb; color: #4b5563; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; padding: 14px 16px; border-bottom: 1px solid #e5e7eb; }
        .table td { padding: 16px; vertical-align: middle; border-bottom: 1px solid #e5e7eb; }
        .article-title { color: #111827; font-weight: 500; text-decoration: none; }
        .article-title:hover { color: #4f46e5; text-decoration: underline; }
        .badge-date { background-color: #f3f4f6; color: #374151; font-weight: 500; padding: 6px 10px; border-radius: 6px; font-size: 12px; }
        .loading-spinner { display: none; text-align: center; margin-top: 25px; }
        .download-btn { padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: 500; }
        .select-all-container { background-color: #f9fafb; padding: 12px 16px; border-radius: 8px; border: 1px solid #e5e7eb; display: flex; align-items: center; justify-content: space-between; margin-top: 25px; }
    </style>
</head>
<body>
    <div class="container mb-5">
        <div class="header">
            <h2><i class="fa-solid fa-book-open text-primary me-2"></i>Makale Toplayıcı</h2>
            <p class="text-muted">Web sitelerindeki makaleleri temiz Markdown (.md) olarak doğrudan indirin</p>
        </div>
        
        <form id="search-form">
            <div class="row g-3">
                <div class="col-md-7">
                    <label class="form-label font-weight-600">Web Sitesi URL</label>
                    <div class="input-group">
                        <span class="input-group-text"><i class="fa-solid fa-link"></i></span>
                        <input type="url" id="base_url" class="form-control" placeholder="https://example.com" required>
                    </div>
                </div>
                <div class="col-md-5">
                    <label class="form-label font-weight-600">Yazar Adı</label>
                    <div class="input-group">
                        <span class="input-group-text"><i class="fa-solid fa-user"></i></span>
                        <input type="text" id="author_name" class="form-control" placeholder="Yazarın tam adı" required>
                    </div>
                </div>
            </div>
            <button type="submit" class="btn btn-primary w-100 mt-4 py-2.5"><i class="fa-solid fa-magnifying-glass me-2"></i>Makaleleri Bul</button>
        </form>

        <div id="loading" class="loading-spinner">
            <div class="spinner-border text-primary mb-2" role="status"></div>
            <p class="text-muted mb-0" id="loading-text">Yazara ait makaleler aranıyor ve bilgileri çekiliyor...</p>
        </div>

        <div id="results-section" style="display: none;">
            <div class="select-all-container">
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="select-all">
                    <label class="form-check-label font-weight-600 ms-1" for="select-all">Tümünü Seç / Seçimi Kaldır</label>
                </div>
                <button id="download-selected-btn" class="btn btn-success btn-sm py-2 px-3"><i class="fa-solid fa-download me-2"></i>Seçilenleri İndir</button>
            </div>

            <div class="table-responsive">
                <table class="table">
                    <thead>
                        <tr>
                            <th style="width: 50px;">Seç</th>
                            <th>Tarih</th>
                            <th>Makale Başlığı</th>
                            <th class="text-end" style="width: 120px;">İşlem</th>
                        </tr>
                    </thead>
                    <tbody id="articles-list">
                    </tbody>
                </table>
            </div>
        </div>

        <div id="empty-state" class="text-center py-5 mt-4 border rounded-3 bg-light" style="display: none;">
            <i class="fa-regular fa-folder-open text-muted fs-1 mb-3"></i>
            <h5 class="text-secondary">Makale Bulunamadı</h5>
            <p class="text-muted mb-0">Belirttiğiniz yazar adına ait herhangi bir makale linki tespit edilemedi.</p>
        </div>
    </div>

    <script>
        document.getElementById('search-form').addEventListener('submit', async function(e) {
            e.preventDefault();

            const baseUrl = document.getElementById('base_url').value.trim();
            const authorName = document.getElementById('author_name').value.trim();

            const loading = document.getElementById('loading');
            const resultsSection = document.getElementById('results-section');
            const emptyState = document.getElementById('empty-state');
            const articlesList = document.getElementById('articles-list');

            loading.style.display = 'block';
            resultsSection.style.display = 'none';
            emptyState.style.display = 'none';
            articlesList.innerHTML = '';
            document.getElementById('select-all').checked = false;

            try {
                const response = await fetch('/list_articles', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ base_url: baseUrl, author_name: authorName })
                });

                const data = await response.json();
                loading.style.display = 'none';

                if (data.success && data.articles && data.articles.length > 0) {
                    data.articles.forEach(article => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>
                                <input class="form-check-input article-checkbox" type="checkbox" value="${encodeURIComponent(article.url)}">
                            </td>
                            <td>
                                <span class="badge-date">${article.date}</span>
                            </td>
                            <td>
                                <a href="${article.url}" target="_blank" class="article-title">${escapeHtml(article.title)}</a>
                            </td>
                            <td class="text-end">
                                <a href="/download?url=${encodeURIComponent(article.url)}" class="btn btn-outline-primary btn-sm download-btn">
                                    <i class="fa-solid fa-download me-1"></i> İndir
                                </a>
                            </td>
                        `;
                        articlesList.appendChild(row);
                    });
                    resultsSection.style.display = 'block';
                } else {
                    emptyState.style.display = 'block';
                }
            } catch (err) {
                loading.style.display = 'none';
                alert('Makaleler listelenirken bir hata oluştu: ' + err.message);
            }
        });

        // Select All handler
        document.getElementById('select-all').addEventListener('change', function(e) {
            const checkboxes = document.querySelectorAll('.article-checkbox');
            checkboxes.forEach(cb => cb.checked = e.target.checked);
        });

        // Download Selected articles
        document.getElementById('download-selected-btn').addEventListener('click', function() {
            const checkedBoxes = document.querySelectorAll('.article-checkbox:checked');
            if (checkedBoxes.length === 0) {
                alert('Lütfen indirmek istediğiniz en az bir makaleyi seçin.');
                return;
            }

            checkedBoxes.forEach((cb, index) => {
                setTimeout(() => {
                    const url = decodeURIComponent(cb.value);
                    const downloadUrl = `/download?url=${encodeURIComponent(url)}`;
                    const a = document.createElement('a');
                    a.href = downloadUrl;
                    a.style.display = 'none';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                }, index * 400); // 400ms delay to avoid blocking downloads
            });
        });

        function escapeHtml(text) {
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/list_articles', methods=['POST'])
def list_articles():
    data = request.get_json() or {}
    base_url = data.get('base_url', '').strip()
    author_name = data.get('author_name', '').strip()

    if not base_url or not author_name:
        return jsonify({'success': False, 'message': 'Lütfen tüm alanları doldurun.'}), 400

    try:
        article_links = find_author_articles(base_url, author_name)
        if not article_links:
            return jsonify({'success': True, 'articles': [], 'message': 'Yazara ait makale bulunamadı.'})

        articles = get_articles_metadata(article_links)

        return jsonify({
            'success': True,
            'articles': articles
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Bir hata oluştu: {str(e)}'}), 500

@app.route('/download')
def download_article():
    url = request.args.get('url')
    if not url:
        return "URL parametresi eksik", 400

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        title = extract_title(soup)
        date = extract_date(soup)
        clean_markdown = extract_clean_content(soup)

        # Format the markdown file content
        final_content = f"# {title}\n\n"
        final_content += f"- **Kaynak:** {url}\n"
        if date and date != "Belirtilmemiş":
            final_content += f"- **Yayınlanma Tarihi:** {date}\n"
        final_content += f"\n---\n\n{clean_markdown}\n"

        # Clean the title for file name
        safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '_', '-')]).strip()
        safe_title = safe_title.replace(' ', '_')
        if not safe_title:
            safe_title = "makale"

        filename = f"{safe_title}.md"

        import unicodedata
        import urllib.parse

        response = Response(final_content.encode('utf-8'), mimetype='text/markdown')

        try:
            filename.encode('ascii')
            response.headers.set('Content-Disposition', 'attachment', filename=filename)
        except UnicodeEncodeError:
            # Create an ASCII fallback filename
            fallback_filename = unicodedata.normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')
            # Replace spaces/special patterns or fallback if it's empty
            fallback_filename = "".join([c for c in fallback_filename if c.isalnum() or c in (' ', '_', '-', '.')]).strip()
            if not fallback_filename or fallback_filename == ".md":
                fallback_filename = "makale.md"

            quoted_filename = urllib.parse.quote(filename)
            response.headers.set('Content-Disposition', 'attachment', filename=fallback_filename, **{'filename*': f"UTF-8''{quoted_filename}"})

        return response

    except Exception as e:
        return f"Makale indirilirken bir hata oluştu: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
