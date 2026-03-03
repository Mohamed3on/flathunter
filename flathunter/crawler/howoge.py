"""Expose crawler for howoge.de (JSON API)"""
import re
from urllib.parse import urlparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger

BASE_URL = "https://www.howoge.de"
API_URL = "https://www.howoge.de/?type=999&tx_howrealestate_json_list[action]=immoList"


def _abs(href):
    if href.startswith("http"):
        return href
    return f"{BASE_URL}/{href.lstrip('/')}"


class Howoge(Crawler):
    """Crawler for howoge.de rental listings (JSON API)"""

    URL_PATTERN = re.compile(r'https://www\.howoge\.de')

    SIMPLE_HEADERS = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    def get_soup_from_url(self, url):
        """Override with simpler headers to avoid redirect loops on howoge.de."""
        resp = requests.get(url, headers=self.SIMPLE_HEADERS, timeout=30)
        return BeautifulSoup(resp.content, 'lxml')

    def _build_post_data(self, search_url):
        """Extract tx_howrealestate_json_list params from URL query string into POST body.
        Returns URL-encoded string to preserve multiple values for array params like kiez[]."""
        qs = parse_qs(urlparse(search_url).query)
        prefix = 'tx_howrealestate_json_list'
        pairs = []
        has_page = has_limit = False
        for key, values in qs.items():
            if not key.startswith(prefix):
                continue
            if '[page]' in key:
                has_page = True
            if '[limit]' in key:
                has_limit = True
            for v in values:
                pairs.append((key, v))
        if not has_page:
            pairs.append((f'{prefix}[page]', '1'))
        if not has_limit:
            pairs.append((f'{prefix}[limit]', '50'))
        return urlencode(pairs)

    def get_results(self, search_url, max_pages=None):
        """Override to POST to JSON API instead of fetching HTML."""
        logger.debug("Howoge: fetching from API for %s", search_url)
        base_body = self._build_post_data(search_url)
        # Extract limit from the encoded body for pagination
        qs_parsed = parse_qs(base_body)
        limit = int(qs_parsed.get('tx_howrealestate_json_list[limit]', ['50'])[0])

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json, text/javascript, */*',
            'X-Requested-With': 'XMLHttpRequest',
        }

        entries = []
        page = 1
        while True:
            # Replace page number in the encoded body
            body = re.sub(
                r'tx_howrealestate_json_list%5Bpage%5D=\d+',
                f'tx_howrealestate_json_list%5Bpage%5D={page}',
                base_body,
            )
            resp = requests.post(API_URL, data=body, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for obj in data.get('immoobjects', []):
                image = None
                if obj.get('image'):
                    image = _abs(obj['image'])

                entries.append({
                    'id': obj['uid'],
                    'url': _abs(obj.get('link', '')),
                    'title': obj.get('title', ''),
                    'price': f"{obj.get('rent', '')} €",
                    'size': f"{obj.get('area', '')} m²",
                    'rooms': str(obj.get('rooms', '')),
                    'address': obj.get('title', ''),
                    'image': image,
                    'crawler': self.get_name(),
                    'district': obj.get('district', ''),
                    'wbs': obj.get('wbs', ''),
                    'features': obj.get('features', []),
                    'notice': obj.get('notice', ''),
                    'warmmiete': obj.get('rent'),
                })

            # Neubauprojekte teasers (only on first page)
            if page == 1:
                for teaser in data.get('projectteaser', []):
                    link = teaser.get('link', '')
                    if not link:
                        continue
                    image = None
                    if teaser.get('image'):
                        image = _abs(teaser['image'])
                    entries.append({
                        'id': hash(link) & 0x7FFFFFFF,
                        'url': _abs(link),
                        'title': teaser.get('title', ''),
                        'price': '',
                        'size': '',
                        'rooms': teaser.get('rooms', ''),
                        'address': teaser.get('address', ''),
                        'image': image,
                        'crawler': self.get_name(),
                        'district': '',
                        'notice': f"Neubauprojekt — Bezug: {teaser.get('indate', '')}",
                    })

            total = data.get('immocount', 0)
            if page * limit >= total:
                break
            page += 1

        logger.debug('Howoge: found %d entries', len(entries))
        return entries

    def get_expose_details(self, expose):
        try:
            soup = self.get_soup_from_url(expose['url'])

            # Description from long paragraphs
            desc_parts = []
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 60 and 'cookie' not in text.lower():
                    desc_parts.append(text)
            if desc_parts:
                expose['detail_description'] = "\n".join(desc_parts)[:2000]

            # Warmmiete from detail table
            for tr in soup.select('table tr'):
                cells = tr.find_all(['th', 'td'])
                if len(cells) == 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if 'Warmmiete' in label:
                        m = re.search(r'[\d.]+,\d+', value)
                        if m:
                            expose['warmmiete'] = float(m.group().replace('.', '').replace(',', '.'))
                        break

            # Photos from fileadmin
            photos = []
            for img in soup.select('img[src*="fileadmin"]'):
                src = img.get('src', '')
                if src and '_processed_' not in src:
                    photos.append(_abs(src))
            # Also grab processed ones if no raw ones
            if not photos:
                for img in soup.select('img[src*="fileadmin"]'):
                    src = img.get('src', '')
                    if src:
                        photos.append(_abs(src))
            photos = list(dict.fromkeys(photos))
            expose['detail_photos'] = photos
            expose['detail_total_photos'] = len(photos)

        except Exception as exc:
            logger.debug("Failed to fetch details for %s: %s", expose.get('url'), exc)
        return expose
