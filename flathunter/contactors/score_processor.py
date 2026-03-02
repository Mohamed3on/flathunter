"""Processor that scores listings with Gemini — parallelized for speed"""
from flathunter.abstract_processor import Processor
from flathunter.contactors.message_generator import score_listings_parallel
from flathunter.logging import logger


class GeminiScoreProcessor(Processor):
    """Enriches exposes with Gemini score, pros, cons, summary, and draft message.
    Parallelizes API calls. Overrides process_exposes (not process_expose)
    because scoring is batched for parallelism."""

    def __init__(self, config):
        self.config = config

    def process_exposes(self, exposes):
        eligible = list(exposes)
        if eligible:
            logger.info("Scoring %d listings with Gemini (parallel)", len(eligible))
            score_listings_parallel(eligible, self.config)
        return iter(eligible)
