"""Expose crawler for wbm.de"""
import re

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger

BASE_URL = "https://www.wbm.de"


def _abs(href):
    if href.startswith("http"):
        return href
    return f"{BASE_URL}/{href.lstrip('/')}"


def _parse_german_price(text):
    """'1.967,80 €' -> 1967.8"""
    m = re.search(r'[\d.]+,\d+', text)
    if not m:
        return None
    return float(m.group().replace('.', '').replace(',', '.'))


class Wbm(Crawler):
    """Crawler for wbm.de rental listings (SSR HTML)"""

    URL_PATTERN = re.compile(r'https://www\.wbm\.de')

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
            url = _abs(link_el.get('href', ''))

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
                    image = _abs(bg)
                elif 'url(' in bg:
                    m = re.search(r'url\(([^)]+)\)', bg)
                    if m:
                        image = _abs(m.group(1))

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

            # Warmmiete already in listing price, but try to get it from detail too
            warmmiete = _parse_german_price(expose.get('price', ''))
            if warmmiete:
                expose['warmmiete'] = warmmiete

            # Description from long paragraphs
            desc_parts = []
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 60 and 'cookie' not in text.lower() and 'datenschutz' not in text.lower():
                    desc_parts.append(text)
            if desc_parts:
                expose['detail_description'] = "\n".join(desc_parts)[:2000]

            # Photos
            photos = []
            for img in soup.select('img[src*="openimmo"], img[src*="uploads/tx_"]'):
                src = img.get('src', '')
                if src:
                    photos.append(_abs(src))
            photos = list(dict.fromkeys(photos))
            expose['detail_photos'] = photos
            expose['detail_total_photos'] = len(photos)

        except Exception as exc:
            logger.debug("Failed to fetch details for %s: %s", expose.get('url'), exc)
        return expose
