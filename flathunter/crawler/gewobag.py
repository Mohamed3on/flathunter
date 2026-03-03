"""Expose crawler for gewobag.de"""
import re

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger


def _parse_german_price(text):
    """'1.100,00€' -> 1100.0"""
    m = re.search(r'[\d.]+,\d+', text)
    if not m:
        return None
    return float(m.group().replace('.', '').replace(',', '.'))


class Gewobag(Crawler):
    """Crawler for gewobag.de rental listings (SSR HTML)"""

    URL_PATTERN = re.compile(r'https://www\.gewobag\.de')

    def extract_data(self, soup):
        entries = []
        for card in soup.select('article.angebot-big-box'):
            footer_link = card.select_one('div.angebot-footer a.read-more-link')
            if not footer_link:
                continue
            url = footer_link.get('href', '')
            if not url:
                continue

            # ID from post-XXXXX id attr
            post_id = card.get('id', '')
            id_match = re.search(r'(\d+)', post_id)
            if not id_match:
                continue
            expose_id = int(id_match.group(1))

            # Table rows
            district = ''
            address = ''
            title = ''
            area = ''
            price = ''
            rooms = ''
            availability = ''

            region_td = card.select_one('tr.angebot-region td')
            if region_td:
                district = region_td.get_text(strip=True)

            addr_td = card.select_one('tr.angebot-address td address')
            if addr_td:
                address = addr_td.get_text(strip=True)

            title_el = card.select_one('tr.angebot-address h3.angebot-title')
            if title_el:
                title = title_el.get_text(strip=True)

            area_td = card.select_one('tr.angebot-area td')
            if area_td:
                area_text = area_td.get_text(strip=True)
                # "3 Zimmer | 76,13 m²"
                area = area_text
                rm = re.search(r'(\d+)\s*Zimmer', area_text)
                if rm:
                    rooms = rm.group(1)

            cost_td = card.select_one('tr.angebot-kosten td')
            if cost_td:
                price = cost_td.get_text(strip=True)

            avail_td = card.select_one('tr.availability td')
            if avail_td:
                availability = avail_td.get_text(strip=True)

            # WBS from pictogram
            wbs = 'nein'
            if card.select_one('.gw-pictogram--wbs'):
                wbs = 'ja'

            # First image
            image = None
            img = card.select_one('.swiper img')
            if img:
                image = img.get('src') or img.get('data-src')

            entries.append({
                'id': expose_id,
                'url': url,
                'title': title or f"{rooms} Zimmer in {district}",
                'price': price,
                'size': area,
                'rooms': rooms,
                'address': address,
                'image': image,
                'crawler': self.get_name(),
                'district': district,
                'wbs': wbs,
                'availability': availability,
            })

        logger.debug('Gewobag: found %d entries', len(entries))
        return entries

    def get_expose_details(self, expose):
        try:
            soup = self.get_soup_from_url(expose['url'])

            # Gesamtmiete from detail table
            for tr in soup.select('table tr'):
                th = tr.find('th')
                td = tr.find('td')
                if th and td:
                    label = th.get_text(strip=True)
                    if 'Gesamtmiete' in label:
                        val = _parse_german_price(td.get_text(strip=True))
                        if val:
                            expose['warmmiete'] = val

            # Description from long paragraphs
            desc_parts = []
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 60 and 'cookie' not in text.lower():
                    desc_parts.append(text)
            if desc_parts:
                expose['detail_description'] = "\n".join(desc_parts)[:2000]

            # Photos from gallery slider
            photos = []
            for img in soup.select('.angebot-slider img, .swiper img'):
                src = img.get('src') or img.get('data-src')
                if src and 'gewo-immo-media' in src:
                    photos.append(src)
            photos = list(dict.fromkeys(photos))
            expose['detail_photos'] = photos
            expose['detail_total_photos'] = len(photos)

        except Exception as exc:
            logger.debug("Failed to fetch details for %s: %s", expose.get('url'), exc)
        return expose
