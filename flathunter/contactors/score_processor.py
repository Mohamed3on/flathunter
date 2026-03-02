"""Processor that scores listings with Gemini — parallelized for speed"""
from flathunter.abstract_processor import Processor
from flathunter.contactors.message_generator import score_listings_parallel
from flathunter.logging import logger


class GeminiScoreProcessor(Processor):
    """Enriches exposes with Gemini score, pros, cons, summary, and draft message.
    Skips listings that failed duration checks. Parallelizes API calls."""

    def __init__(self, config):
        self.config = config

    def process_expose(self, expose):
        return expose

    def process_exposes(self, exposes):
        """Collect exposes, filter out bad durations, score the rest in parallel."""
        eligible = []
        skipped = []
        for expose in exposes:
            if expose.get('durations_passed', True) is False:
                logger.info("Skipping Gemini scoring for '%s' — durations exceed limits",
                            expose.get('title'))
                skipped.append(expose)
            else:
                eligible.append(expose)

        if eligible:
            logger.info("Scoring %d listings with Gemini (parallel), skipped %d (bad durations)",
                         len(eligible), len(skipped))
            score_listings_parallel(eligible, self.config, max_workers=10)

        return iter(skipped + eligible)
