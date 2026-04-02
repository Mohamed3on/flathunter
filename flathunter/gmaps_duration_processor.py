"""Calculate travel durations using Google Maps (primary) with free fallbacks.
Fallbacks: OSRM for driving/bicycling, BVG transport.rest for transit."""
import datetime
import time
from datetime import timezone
from urllib.parse import quote_plus
import requests

from flathunter.logging import logger
from flathunter.abstract_processor import Processor

AVG_CYCLING_SPEED_MS = 16 * 1000 / 3600  # 16 km/h in m/s


class GMapsDurationProcessor(Processor):
    """Implementation of Processor class to calculate travel durations"""

    GM_MODE_TRANSIT = 'transit'
    GM_MODE_BICYCLE = 'bicycling'
    GM_MODE_DRIVING = 'driving'

    def __init__(self, config):
        self.config = config
        self._google_quota_exhausted = False

    def process_expose(self, expose):
        """Calculate the durations for an expose"""
        if expose.get('address') is None:
            expose['durations'] = ''
            expose['durations_passed'] = False
            return expose
        durations_str, any_passed = self.get_formatted_durations(expose['address'])
        expose['durations'] = durations_str.strip()
        expose['durations_passed'] = any_passed
        return expose

    def get_formatted_durations(self, address):
        """Return a formatted list of durations and whether any passed limits"""
        out = ""
        any_passed = False
        for dest_config in self.config.get('durations', []):
            if 'destination' not in dest_config or 'name' not in dest_config:
                continue

            dest = dest_config.get('destination')
            name = dest_config.get('name')
            max_duration = dest_config.get('max_duration')
            any_within_limit = False
            all_within_max = True
            for mode in dest_config.get('modes', []):
                if 'gm_id' not in mode or 'title' not in mode:
                    continue

                duration = self._get_duration(address, dest, mode['gm_id'])
                title = mode['title']
                duration_minutes = self.duration_to_minutes(duration)
                limit = mode.get('limit', None)

                if limit is not None and duration_minutes is not None and 0 < duration_minutes <= limit:
                    format_style = "b"
                    emoji = "✅"
                    any_within_limit = True
                else:
                    format_style = "i"
                    emoji = "❌"

                if max_duration and duration_minutes and duration_minutes > max_duration:
                    all_within_max = False

                out += f"> {name} ({title}): {emoji} <{format_style}>{duration}</{format_style}>\n"

            if any_within_limit and all_within_max:
                any_passed = True

        return out.strip(), any_passed

    def _get_duration(self, address, dest, mode):
        """Try Google Maps first, fall back to free APIs on quota exhaustion."""
        if not self._google_quota_exhausted:
            result = self._get_gmaps_distance(address, dest, mode)
            if result is not None:
                return result
            if self._google_quota_exhausted:
                logger.info("Google Maps quota exhausted — switching to free fallbacks")

        return self._get_fallback_duration(address, dest, mode)

    def duration_to_minutes(self, duration_text):
        """Convert duration string to minutes"""
        if duration_text is None:
            return None

        tokens = duration_text.split()
        minutes = 0
        for i in range(len(tokens)):
            if tokens[i] in ('h', 'hour', 'hours'):
                minutes += int(tokens[i - 1]) * 60
            elif tokens[i] in ('mins', 'min'):
                minutes += int(tokens[i - 1])

        return minutes

    # --- Google Maps (primary) ---

    def _get_gmaps_distance(self, address, dest, mode):
        """Get duration from Google Distance Matrix API. Returns None and sets
        _google_quota_exhausted on OVER_QUERY_LIMIT."""
        base_url = self.config.get('google_maps_api', {}).get('url')
        gm_key = self.config.get('google_maps_api', {}).get('key')

        if not base_url or not gm_key:
            self._google_quota_exhausted = True
            return None

        now = datetime.datetime.today().replace(hour=9, minute=0, second=0)
        next_monday = now + datetime.timedelta(days=7 - now.weekday())
        arrival_time = str(int(time.mktime(next_monday.timetuple())))

        address_enc = quote_plus(address.strip().encode('utf8'))
        dest_enc = quote_plus(dest.strip().encode('utf8'))

        url = base_url.format(dest=dest_enc, mode=mode, origin=address_enc,
                              key=gm_key, arrival=arrival_time)
        result = requests.get(url, timeout=30).json()

        if result['status'] in ('OVER_QUERY_LIMIT', 'REQUEST_DENIED'):
            self._google_quota_exhausted = True
            return None
        if result['status'] != 'OK':
            logger.error("Google Maps error for %s: %s", address, result)
            return None

        distances = {}
        for row in result['rows']:
            for element in row['elements']:
                if element.get('status') != 'OK':
                    continue
                distances[element['duration']['value']] = (
                    f"{element['duration']['text']} ({element['distance']['text']})"
                )
        return distances[min(distances.keys())] if distances else None

    # --- Free fallbacks ---

    def _geocode(self, address):
        """Geocode address to (lat, lng) via BVG transport.rest."""
        resp = requests.get("https://v6.bvg.transport.rest/locations", params={
            "query": address, "addresses": True, "results": 1,
        }, timeout=10)
        resp.raise_for_status()
        loc = resp.json()[0]
        return loc["latitude"], loc["longitude"]

    def _get_fallback_duration(self, address, dest, mode):
        """Route via OSRM (driving/bicycling) or BVG transport.rest (transit)."""
        try:
            origin_coords = self._geocode(address)
            dest_coords = self._geocode(dest)
        except Exception:
            logger.warning("Fallback geocoding failed for %s", address)
            return None

        if mode == self.GM_MODE_TRANSIT:
            return self._bvg_transit(origin_coords, dest_coords, address, dest)
        else:
            return self._osrm_route(origin_coords, dest_coords, mode)

    def _osrm_route(self, origin, dest, mode):
        """Get driving/cycling duration from OSRM (free, no key)."""
        try:
            url = (f"https://router.project-osrm.org/route/v1/driving/"
                   f"{origin[1]},{origin[0]};{dest[1]},{dest[0]}?overview=false")
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data["code"] != "Ok" or not data["routes"]:
                return None
            route = data["routes"][0]
            distance_m = route["distance"]
            if mode == self.GM_MODE_BICYCLE:
                duration_s = distance_m / AVG_CYCLING_SPEED_MS
            else:
                duration_s = route["duration"]
            distance_km = distance_m / 1000
            mins = int(duration_s // 60)
            return f"{mins} min ({distance_km:.1f} km)"
        except Exception:
            logger.warning("OSRM fallback failed")
            return None

    def _bvg_transit(self, origin, dest, origin_address, dest_address):
        """Get transit duration from BVG transport.rest (free, no key)."""
        try:
            resp = requests.get("https://v6.bvg.transport.rest/journeys", params={
                "from.latitude": origin[0], "from.longitude": origin[1],
                "from.address": origin_address,
                "to.latitude": dest[0], "to.longitude": dest[1],
                "to.address": dest_address,
                "results": 3,
            }, timeout=15)
            resp.raise_for_status()
            journeys = resp.json().get("journeys", [])
            if not journeys:
                return None
            best = None
            for j in journeys:
                dep = datetime.datetime.fromisoformat(j["legs"][0]["departure"])
                arr = datetime.datetime.fromisoformat(j["legs"][-1]["arrival"])
                secs = int((arr - dep).total_seconds())
                if best is None or secs < best:
                    best = secs
            mins = best // 60
            return f"{mins} min"
        except Exception:
            logger.warning("BVG transit fallback failed")
            return None
