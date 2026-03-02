"""Utility classes for building chains for processors"""
from functools import reduce
from typing import List

from flathunter.default_processors import AddressResolver
from flathunter.default_processors import FilterProcessor
from flathunter.default_processors import LambdaProcessor
from flathunter.default_processors import CrawlExposeDetails
from flathunter.filter import ExposeHelper
from flathunter.notifiers import SenderTelegram, SenderApprise
from flathunter.gmaps_duration_processor import GMapsDurationProcessor
from flathunter.contactors.auto_contact import AutoContactProcessor
from flathunter.contactors.score_processor import GeminiScoreProcessor
from flathunter.abstract_processor import Processor
from flathunter.logging import logger

class SaveAllExposesProcessor(Processor):
    """Processor that saves all exposes to the database"""

    def __init__(self, config, id_watch):
        self.config = config
        self.id_watch = id_watch

    def process_expose(self, expose):
        """Save a single expose"""
        self.id_watch.save_expose(expose)
        return expose


class QualityFilter(Processor):
    """Drop exposes that fail duration limits or exceed PPS threshold.
    Should run after calculate_durations and crawl_expose_details."""

    def __init__(self, config):
        self.config = config
        self.max_pps = config.telegram_preferred_max_pps()

    def process_exposes(self, exposes):
        for expose in exposes:
            if not expose.get('durations_passed', True):
                logger.info("Dropping '%s': durations exceed limits", expose.get('title'))
                continue
            if self.max_pps:
                price = ExposeHelper.get_price(expose)
                size = ExposeHelper.get_size(expose)
                if price and size and price / size > self.max_pps:
                    logger.info("Dropping '%s': PPS %.1f exceeds %.1f",
                                expose.get('title'), price / size, self.max_pps)
                    continue
            yield expose


class ProcessorChainBuilder:
    """Builder pattern for building chains of processors"""
    processors: List[Processor]

    def __init__(self, config):
        self.processors = []
        self.config = config

    def send_messages(self, receivers=None):
        """Add processor that sends messages for exposes"""
        notifiers = self.config.notifiers()
        if 'telegram' in notifiers:
            self.processors.append(SenderTelegram(self.config, receivers=receivers))
        if 'apprise' in notifiers:
            self.processors.append(SenderApprise(self.config))
        return self

    def resolve_addresses(self):
        """Add processor that resolves addresses from expose pages"""
        self.processors.append(AddressResolver(self.config))
        return self

    def calculate_durations(self):
        """Add processor to calculate durations, if enabled"""
        durations_enabled = "google_maps_api" in self.config \
                            and self.config["google_maps_api"]["enable"]
        if durations_enabled:
            self.processors.append(GMapsDurationProcessor(self.config))
        return self

    def crawl_expose_details(self):
        """Add processor to crawl expose details"""
        self.processors.append(CrawlExposeDetails(self.config))
        return self

    def filter_quality(self):
        """Drop exposes that fail duration limits or exceed PPS threshold"""
        self.processors.append(QualityFilter(self.config))
        return self

    def map(self, func):
        """Add processor that applies a lambda to exposes"""
        self.processors.append(LambdaProcessor(self.config, func))
        return self

    def apply_filter(self, filter_set):
        """Add processor that applies a filter to expose sequence"""
        self.processors.append(FilterProcessor(self.config, filter_set))
        return self

    def save_all_exposes(self, id_watch):
        """Add processor that saves all exposes to disk"""
        self.processors.append(SaveAllExposesProcessor(self.config, id_watch))
        return self

    def score_with_gemini(self):
        """Add processor that scores listings with Gemini, if enabled"""
        if self.config.auto_contact_gemini_api_key():
            self.processors.append(GeminiScoreProcessor(self.config))
        return self

    def auto_contact(self, id_watch):
        """Add processor that auto-contacts landlords, if enabled"""
        if self.config.auto_contact_enabled():
            self.processors.append(AutoContactProcessor(self.config, id_watch))
        return self

    def build(self):
        """Build the processor chain"""
        return ProcessorChain(self.processors)

class ProcessorChain:
    """Class to hold a chain of processors"""
    processors: List[Processor]

    def __init__(self, processors):
        self.processors = processors

    def process(self, exposes):
        """Process the sequences of exposes with the processor chain"""
        return reduce((lambda exposes, processor: processor.process_exposes(exposes)),
                      self.processors, exposes)

    @staticmethod
    def builder(config):
        """Return a new processor chain builder"""
        return ProcessorChainBuilder(config)
