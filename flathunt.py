#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Flathunter — local CLI entry point."""
from flathunter.logging import logger
from flathunter.startup import create_hunter


def main():
    hunter = create_hunter()
    config = hunter.config

    notifiers = config.notifiers()
    if 'telegram' in notifiers:
        if not config.telegram_bot_token():
            logger.error("No Telegram bot token configured.")
            return
        if len(config.telegram_receiver_ids()) == 0:
            logger.warning("No Telegram receivers configured — nobody will get notifications.")
    if len(config.target_urls()) == 0:
        logger.error("No URLs configured.")
        return

    hunter.hunt_flats()


if __name__ == "__main__":
    main()
