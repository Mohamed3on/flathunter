"""Shared startup logic for CLI and Cloud Run entry points"""
from flathunter.argument_parser import parse
from flathunter.config import Config
from flathunter.googlecloud_idmaintainer import GoogleCloudIdMaintainer
from flathunter.hunter import Hunter
from flathunter.logging import configure_logging


def create_hunter() -> Hunter:
    """Parse args, build config, and return a ready-to-run Hunter."""
    args = parse()
    config_handle = args.config
    config = Config(config_handle.name) if config_handle else Config()

    configure_logging(config)
    config.init_searchers()

    id_watch = GoogleCloudIdMaintainer(config)
    return Hunter(config, id_watch)
