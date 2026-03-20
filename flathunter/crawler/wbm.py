"""Expose crawler for wbm.de"""
import re

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger
from flathunter.utils import parse_german_price


class Wbm(Crawler):
    """Crawler for wbm.de rental listings (SSR HTML)"""

    URL_PATTERN = re.compile(r'https://www\.wbm\.de')
    BASE_URL = "https://www.wbm.de"

    def extract_data(self, soup):
        entries = []
        for card in soup.select('div.row.openimmo-search-list-item'):
            uid = card.get('data-uid', '')
            if not uid:
                continue
            expose_id = int(uid)

            # Detail link
            link_el = card.select_one('a.immo-button-cta') or card.select_one('a.btn.sign')
            if not link_el:
                continue
            url = self._abs(link_el.get('href', ''))

            title = ''
            h2 = card.select_one('h2.imageTitle')
            if h2:
                title = h2.get_text(strip=True)

            address = ''
            addr_el = card.select_one('div.address')
            if addr_el:
                address = addr_el.get_text(strip=True)

            district = ''
            area_el = card.select_one('div.area')
            if area_el:
                district = area_el.get_text(strip=True)

            # Main properties: rent, size, rooms
            price = ''
            size = ''
            rooms = ''
            for li in card.select('li.main-property'):
                val_el = li.select_one('.main-property-value')
                if not val_el:
                    continue
                val = val_el.get_text(strip=True)
                if 'main-property-rent' in val_el.get('class', []):
                    price = val
                elif 'main-property-size' in val_el.get('class', []):
                    size = val
                elif 'main-property-rooms' in val_el.get('class', []):
                    rooms = val

            # Amenities
            amenities = [li.get_text(strip=True) for li in card.select('ul.check-property-list li')]

            # Image
            image = None
            img_wrap = card.select_one('div.imgWrap')
            if img_wrap:
                bg = img_wrap.get('data-img-src') or img_wrap.get('style', '')
                if bg.startswith('/'):
                    image = self._abs(bg)
                elif 'url(' in bg:
                    m = re.search(r'url\(([^)]+)\)', bg)
                    if m:
                        image = self._abs(m.group(1))

            entries.append({
                'id': expose_id,
                'url': url,
                'title': title,
                'price': price,
                'size': size,
                'rooms': rooms,
                'address': address,
                'image': image,
                'crawler': self.get_name(),
                'district': district,
                'amenities': amenities,
            })

        logger.debug('Wbm: found %d entries', len(entries))
        return entries

    def get_expose_details(self, expose):
        try:
            soup = self.get_soup_from_url(expose['url'])

            warmmiete = parse_german_price(expose.get('price', ''))
            if warmmiete:
                expose['warmmiete'] = warmmiete

            desc = self._extract_description(soup, extra_excludes=('datenschutz',))
            if desc:
                expose['detail_description'] = desc

            photos = []
            for img in soup.select('img[src*="openimmo"], img[src*="uploads/tx_"]'):
                src = img.get('src', '')
                if src:
                    photos.append(self._abs(src))
            self._set_photos(expose, photos)

        except Exception as exc:
            logger.debug("Failed to fetch details for %s: %s", expose.get('url'), exc)
        return expose
