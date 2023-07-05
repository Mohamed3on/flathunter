import unittest
from flathunter.crawler.meinestadt import CrawlMeineStadt
from test.utils.config import StringConfig


class MeineStadtCrawlerTest(unittest.TestCase):

    TEST_URL = 'https://www.meinestadt.de/freiburg-im-breisgau/immobilien'
    DUMMY_CONFIG = """
    urls:
        - https://www.meinestadt.de/freiburg-im-breisgau/immobilien
    """

    def setUp(self):
        self.crawler = CrawlMeineStadt(StringConfig(string=self.DUMMY_CONFIG))

    def test(self):
        soup = self.crawler.get_page(self.TEST_URL)
        self.assertIsNotNone(soup, "Should get a soup from the URL")
        entries = self.crawler.extract_data(soup)
        self.assertIsNotNone(entries, "Should parse entries from search URL")
        self.assertTrue(len(entries) > 0, "Should have at least one entry")
        self.assertTrue(entries[0]['id'] > 0, "Id should be parsed")
        self.assertTrue(entries[0]['url'].startswith(
            "https://www.meinestadt.de/expose"), u"URL should be an apartment link")
        for attr in ['title', 'price', 'size', 'rooms', 'address', 'image']:
            self.assertIsNotNone(entries[0][attr], attr + " should be set")
