import unittest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
import app

class TestApp(unittest.TestCase):
    def setUp(self):
        self.app = app.app.test_client()
        self.app.testing = True

    def test_index_route(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Makale Toplay', response.data)

    def test_list_articles_missing_params(self):
        response = self.app.post('/list_articles', json={})
        self.assertEqual(response.status_code, 400)
        # Check decoded content
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['message'], 'Lütfen tüm alanları doldurun.')

    @patch('app.requests.get')
    def test_list_articles_success(self, mock_get):
        # Mocking the base URL page
        mock_response = MagicMock()
        mock_response.text = """
            <html>
                <body>
                    <p>Yazar: Ahmet Yılmaz</p>
                    <article>
                        <h2><a href="/makale1">Makale Başlığı 1</a></h2>
                    </article>
                    <article>
                        <h2><a href="/makale2">Makale Başlığı 2</a></h2>
                    </article>
                </body>
            </html>
        """
        mock_response.status_code = 200

        # Mocking metadata fetches for articles
        mock_art1 = MagicMock()
        mock_art1.text = """
            <html>
                <head>
                    <title>Gerçek Başlık 1</title>
                    <meta property="article:published_time" content="2023-10-15">
                </head>
                <body>
                    <article>İçerik buraya gelecek.</article>
                </body>
            </html>
        """
        mock_art1.status_code = 200

        mock_art2 = MagicMock()
        mock_art2.text = """
            <html>
                <head>
                    <title>Gerçek Başlık 2</title>
                    <meta property="article:published_time" content="2023-11-20">
                </head>
                <body>
                    <article>İkinci makalenin içeriği.</article>
                </body>
            </html>
        """
        mock_art2.status_code = 200

        def side_effect(url, *args, **kwargs):
            if '/makale1' in url:
                return mock_art1
            elif '/makale2' in url:
                return mock_art2
            else:
                return mock_response

        mock_get.side_effect = side_effect

        response = self.app.post('/list_articles', json={
            'base_url': 'https://ornek.com',
            'author_name': 'Ahmet'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['articles']), 2)

        # Sort items or find them
        titles = [a['title'] for a in data['articles']]
        self.assertIn('Gerçek Başlık 1', titles)
        self.assertIn('Gerçek Başlık 2', titles)

        dates = [a['date'] for a in data['articles']]
        self.assertIn('2023-10-15', dates)
        self.assertIn('2023-11-20', dates)

    @patch('app.requests.get')
    def test_download_article_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = """
            <html>
                <head>
                    <title>Harika Bir Yazı</title>
                    <meta property="article:published_time" content="2023-12-01">
                </head>
                <body>
                    <nav>Menu linkleri</nav>
                    <article>
                        <h1>Harika Bir Yazı</h1>
                        <p>Bu makalenin asıl içeriğidir.</p>
                    </article>
                    <footer>Alt Bilgi</footer>
                </body>
            </html>
        """
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        response = self.app.get('/download?url=https://ornek.com/yazi1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/markdown')
        self.assertIn('attachment', response.headers.get('Content-Disposition'))

        content_decoded = response.data.decode('utf-8')
        self.assertIn('# Harika Bir Yazı', content_decoded)
        self.assertIn('Yayınlanma Tarihi:** 2023-12-01', content_decoded)
        self.assertIn('Bu makalenin asıl içeriğidir.', content_decoded)
        # Verify navigation and footer were cleaned
        self.assertNotIn('Menu linkleri', content_decoded)
        self.assertNotIn('Alt Bilgi', content_decoded)

if __name__ == '__main__':
    unittest.main()
