"""One-off backfill: re-process specific ImmoScout24 exposes through the full pipeline.
Skips the 'already seen' filter so these get durations, details, quality filter,
Gemini scoring, notifications, and auto-contact."""

from flathunter.config import Config
from flathunter.googlecloud_idmaintainer import GoogleCloudIdMaintainer
from flathunter.logging import configure_logging, logger
from flathunter.processor import ProcessorChain

EXPOSES = [
    {"id": 165814217, "title": "Richardstr. 60", "address": "Richardstr. 60, 12055 Berlin", "price": "2.039", "size": "102,48", "rooms": "3", "crawler": "Immobilienscout"},
    {"id": 165955581, "title": "Magdalenenstraße 21", "address": "Magdalenenstraße 21, 10365 Berlin", "price": "2.062", "size": "102,5", "rooms": "4", "crawler": "Immobilienscout"},
    {"id": 160780133, "title": "Lückstraße 35", "address": "Lückstraße 35, 10317 Berlin", "price": "1.721", "size": "93", "rooms": "4", "crawler": "Immobilienscout"},
    {"id": 164906644, "title": "Gustav-Adolf-Straße 114", "address": "Gustav-Adolf-Straße 114, 13086 Berlin", "price": "1.915", "size": "96,56", "rooms": "3", "crawler": "Immobilienscout"},
    {"id": 165839296, "title": "Petersburger Str. 40", "address": "Petersburger Str. 40, 10249 Berlin", "price": "1.890", "size": "120", "rooms": "3", "crawler": "Immobilienscout"},
    {"id": 165581878, "title": "Stephanstr. 6", "address": "Stephanstr. 6, 10559 Berlin", "price": "1.849", "size": "93,69", "rooms": "3", "crawler": "Immobilienscout"},
    {"id": 165713560, "title": "Berliner Allee 81-83", "address": "Berliner Allee 81-83, 13088 Berlin", "price": "1.632", "size": "112,53", "rooms": "3", "crawler": "Immobilienscout"},
    {"id": 164880492, "title": "Alt-Friedrichsfelde 98", "address": "Alt-Friedrichsfelde 98, 10315 Berlin", "price": "1.499", "size": "94,5", "rooms": "4", "crawler": "Immobilienscout"},
    {"id": 165907460, "title": "13353 Berlin", "address": "13353 Berlin", "price": "1.690", "size": "134", "rooms": "4", "crawler": "Immobilienscout"},
    {"id": 165966421, "title": "Hedwig-Porschütz-Str. 13", "address": "Hedwig-Porschütz-Str. 13, 10557 Berlin", "price": "1.918", "size": "108,58", "rooms": "3", "crawler": "Immobilienscout"},
    {"id": 165969707, "title": "13086 Berlin", "address": "13086 Berlin", "price": "1.656", "size": "97,63", "rooms": "3", "crawler": "Immobilienscout"},
    {"id": 165708412, "title": "Rostocker Str. 14", "address": "Rostocker Str. 14, 10553 Berlin", "price": "1.995", "size": "100,95", "rooms": "3", "crawler": "Immobilienscout"},
    {"id": 166026966, "title": "Forddamm 7", "address": "Forddamm 7, 12107 Berlin", "price": "1.281", "size": "106,58", "rooms": "4", "crawler": "Immobilienscout"},
]

# Add URL to each expose
for e in EXPOSES:
    e["url"] = f"https://www.immobilienscout24.de/expose/{e['id']}"

config = Config("config.yaml")
configure_logging(config)
config.init_searchers()
id_watch = GoogleCloudIdMaintainer(config)

# Pipeline: durations → details → quality filter → Gemini → notify → auto-contact
# No save_all, no filter_already_seen
chain = (
    ProcessorChain.builder(config)
    .resolve_addresses()
    .crawl_expose_details()
    .filter_pre_duration()
    .calculate_durations()
    .filter_durations()
    .score_with_gemini()
    .send_messages()
    .auto_contact(id_watch)
    .build()
)

results = []
for expose in chain.process(iter(EXPOSES)):
    logger.info("Backfilled: %s (score=%s)", expose["title"], expose.get("gemini_score", "N/A"))
    results.append(expose)

logger.info("Done. %d exposes passed quality filter and were processed.", len(results))
