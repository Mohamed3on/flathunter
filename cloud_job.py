""" Startup file for Google Cloud deployment"""
from flathunter.argument_parser import parse
from flathunter.googlecloud_idmaintainer import GoogleCloudIdMaintainer
from flathunter.hunter import Hunter
from flathunter.config import Config
from flathunter.logging import configure_logging

# load config
args = parse()
config_handle = args.config
if config_handle is not None:
    config = Config(config_handle.name)
else:
    config = Config()

id_watch = GoogleCloudIdMaintainer(config)

configure_logging(config)

config.init_searchers()

hunter = Hunter(config, id_watch)

hunter.hunt_flats()
