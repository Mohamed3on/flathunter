#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Flathunter - search for flats by crawling property portals, and receive telegram
   messages about them. Local CLI entry point."""

from flathunter.argument_parser import parse
from flathunter.logging import logger, configure_logging
from flathunter.googlecloud_idmaintainer import GoogleCloudIdMaintainer
from flathunter.hunter import Hunter
from flathunter.config import Config


def main():
    """Processes command-line arguments, loads the config, launches the flathunter"""
    args = parse()
    config_handle = args.config
    if config_handle is not None:
        config = Config(config_handle.name)
    else:
        config = Config()

    configure_logging(config)
    config.init_searchers()

    notifiers = config.notifiers()
    if 'telegram' in notifiers:
        if not config.telegram_bot_token():
            logger.error("No Telegram bot token configured.")
            return
        if len(config.telegram_receiver_ids()) == 0:
            logger.warning("No Telegram receivers configured - nobody will get notifications.")
    if 'apprise' in notifiers and not config.get('apprise', {}):
        logger.error("No apprise url configured.")
        return

    if len(config.target_urls()) == 0:
        logger.error("No URLs configured.")
        return

    id_watch = GoogleCloudIdMaintainer(config)
    hunter = Hunter(config, id_watch)
    hunter.hunt_flats()


if __name__ == "__main__":
    main()
