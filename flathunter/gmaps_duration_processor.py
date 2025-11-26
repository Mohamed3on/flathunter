"""Calculate Google-Maps distances between specific locations and the target flat"""
import datetime
import time
from urllib.parse import quote_plus
import requests

from flathunter.logging import logger
from flathunter.abstract_processor import Processor

class GMapsDurationProcessor(Processor):
    """Implementation of Processor class to calculate travel durations"""

    GM_MODE_TRANSIT = 'transit'
    GM_MODE_BICYCLE = 'bicycling'
    GM_MODE_DRIVING = 'driving'

    def __init__(self, config):
        self.config = config

    def process_expose(self, expose):
        """Calculate the durations for an expose"""
        if expose.get('address') is None:
            expose['durations'] = ''
            return expose
        expose['durations'] = self.get_formatted_durations(expose['address']).strip()
        return expose

    def get_formatted_durations(self, address):
        """Return a formatted list of GoogleMaps durations"""
        out = ""
        for duration in self.config.get('durations', []):
            if 'destination' not in duration or 'name' not in duration:
                continue

            dest = duration.get('destination')
            name = duration.get('name')
            for mode in duration.get('modes', []):
                if not ('gm_id' in mode and 'title' in mode and 'key' in self.config.get('google_maps_api', {})):
                    continue

                duration = self.get_gmaps_distance(address, dest, mode['gm_id'])
                title = mode['title']
                duration_minutes = self.duration_to_minutes(duration)
                limit = mode.get('limit', None)

                if limit is not None and duration_minutes is not None and 0 < duration_minutes <= limit:
                    format_style = "b"
                else:
                    format_style = "i"

                out += f"> {name} ({title}): <{format_style}>{duration}</{format_style}>\n"

        return out.strip()


    def duration_to_minutes(self, duration_text):
        """Convert duration string to minutes"""
        if duration_text is None:
            return None

        tokens = duration_text.split()
        minutes = 0
        for i in range(len(tokens)):
            if tokens[i] == 'h':
                minutes += int(tokens[i - 1]) * 60
            elif tokens[i] == 'mins':
                minutes += int(tokens[i - 1])

        return minutes

    def get_gmaps_distance(self, address, dest, mode):
        """Get the distance"""
        # get timestamp for next monday at 9:00:00 o'clock
        now = datetime.datetime.today().replace(hour=9, minute=0, second=0)
        next_monday = now + datetime.timedelta(days=7 - now.weekday())
        arrival_time = str(int(time.mktime(next_monday.timetuple())))

        # decode from unicode and url encode addresses
        address = quote_plus(address.strip().encode('utf8'))
        dest = quote_plus(dest.strip().encode('utf8'))
        logger.debug("Got address: %s", address)

        # get google maps config stuff
        base_url = self.config.get('google_maps_api', {}).get('url')
        gm_key = self.config.get('google_maps_api', {}).get('key')

        if not gm_key and mode != self.GM_MODE_DRIVING:
            logger.warning("No Google Maps API key configured and without using a mode "
                                 "different from 'driving' is not allowed. "
                                 "Downgrading to mode 'drinving' thus. ")
            mode = 'driving'
            base_url = base_url.replace('&key={key}', '')

        # retrieve the result
        url = base_url.format(dest=dest, mode=mode, origin=address,
                              key=gm_key, arrival=arrival_time)
        result = requests.get(url, timeout=30).json()
        if result['status'] != 'OK':
            logger.error("Failed retrieving distance to address %s: %s", address, result)
            return None

        # get the fastest route
        distances = {}
        for row in result['rows']:
            for element in row['elements']:
                if 'status' in element and element['status'] != 'OK':
                    logger.warning("For address %s we got the status message: %s",
                                         address, element['status'])
                    logger.debug("We got this result: %s", repr(result))
                    continue
                logger.debug("Got distance and duration: %s / %s (%i seconds)",
                                   element['distance']['text'],
                                   element['duration']['text'],
                                   element['duration']['value'])
                duration_text = element['duration']['text']
                distance_text = element['distance']['text']
                distances[element['duration']['value']] = f"{duration_text} ({distance_text})"
        return distances[min(distances.keys())] if distances else None
