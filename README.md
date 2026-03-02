# Flathunter

A bot to help people with their rental real-estate search in Germany. Crawls property listing sites, filters results, optionally scores them with Gemini, and notifies you via Telegram.

## Supported Sites

- [ImmoScout24](https://www.immobilienscout24.de/) (via mobile API)
- [WG-Gesucht](https://www.wg-gesucht.de/)
- [Kleinanzeigen](https://www.kleinanzeigen.de/)

## Features

- Crawls multiple listing sites on a schedule (Cloud Run Job)
- Filters by price, size, rooms, title keywords
- Calculates commute durations via Google Maps
- Fetches full listing details (description, photos, Warmmiete)
- Filters by price-per-sqm and commute duration limits
- AI scoring with Gemini (pros/cons/summary per listing)
- Auto-contacts landlords on ImmoScout24 and WG-Gesucht
- Sends notifications via Telegram (with images) or Apprise
- Stores processed listings in Firestore (no local database)

## Pipeline

```
crawl → save → filter(price/size/rooms/title) → resolve addresses
→ calculate durations → fetch expose details (warmmiete)
→ quality filter (duration + PPS) → Gemini score → notify → auto-contact
```

## Setup

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (for dependency management)
- A Telegram bot token ([BotFather](https://telegram.me/BotFather))
- A Google Cloud project with Firestore in Native mode

### Install

```sh
uv pip install -r requirements.txt
```

### Configuration

Copy `config.yaml.dist` to `config.yaml` and edit it. Key sections:

**URLs** — Visit a property portal, configure your search, copy the results URL:

```yaml
urls:
  - https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-mieten?...
  - https://www.wg-gesucht.de/wohnungen-in-Berlin.8.2.1.0.html
```

**Telegram:**

```yaml
telegram:
  bot_token: "YOUR_BOT_TOKEN"
  receiver_ids:
    - 12345678
  notify_with_images: true
  preferred_max_pps: 18.0  # price per sqm threshold for visual indicator
```

To find your Chat ID, send a message to your bot, then:
```sh
curl https://api.telegram.org/bot[BOT-TOKEN]/getUpdates
```

**Filters:**

```yaml
filters:
  min_price: 800
  max_price: 2000
  min_size: 60
  max_size: 120
  min_rooms: 2
  max_rooms: 4
  excluded_titles:
    - "WBS"
    - "Tausch"
```

**Google Maps** (optional — for commute duration calculation):

```yaml
google_maps_api:
  enable: true
  key: "YOUR_GOOGLE_MAPS_API_KEY"
  url: "https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin}&destinations={dest}&mode={mode}&arrival_time={arrival}&key={key}"

durations:
  - destination: "Alexanderplatz, Berlin"
    name: "Office"
    modes:
      - gm_id: transit
        title: Transit
        limit: 40
```

**Auto-contact** (optional — auto-message landlords):

```yaml
auto_contact:
  enabled: true
  dry_run: false
  gemini_api_key: "YOUR_GEMINI_API_KEY"
  gemini_prompt: "Write a friendly message..."
  user_profile: "I am a ..."
  immoscout:
    first_name: "..."
    last_name: "..."
    email: "..."
  wg_gesucht:
    email: "..."
    password: "..."
```

### Run Locally

```sh
python flathunt.py --config config.yaml
```

## Cloud Deployment (Google Cloud Run)

The app is designed to run as a Cloud Run Job, triggered on a schedule by Cloud Scheduler.

### Deploy

Push to `main` triggers the GitHub Actions workflow (`.github/workflows/deploy.yml`) which:

1. Builds the Docker image from `Dockerfile.gcloud.job`
2. Pushes to GCR
3. Updates the config secret in Secret Manager
4. Creates/updates the Cloud Run Job
5. Ensures a Cloud Scheduler trigger exists (every 10 min)

### Manual deploy

```sh
docker build -t flathunter-job -f Dockerfile.gcloud.job .
gcloud builds submit --region=europe-west1
```

### Environment Variables

Most config options can be set via environment variables:

| Variable | Description |
|---|---|
| `FLATHUNTER_TARGET_URLS` | Semicolon-separated list of URLs to crawl |
| `FLATHUNTER_GOOGLE_CLOUD_PROJECT_ID` | Google Cloud Project ID |
| `FLATHUNTER_VERBOSE_LOG` | Set to any value for verbose logging |
| `FLATHUNTER_MESSAGE_FORMAT` | Notification message format (`#CR#` = newline) |
| `FLATHUNTER_NOTIFIERS` | Comma-separated list (e.g. `telegram,apprise`) |
| `FLATHUNTER_TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `FLATHUNTER_TELEGRAM_RECEIVER_IDS` | Comma-separated receiver IDs |
| `FLATHUNTER_FILTER_EXCLUDED_TITLES` | Semicolon-separated excluded title words |
| `FLATHUNTER_FILTER_MIN_PRICE` | Minimum price (euros) |
| `FLATHUNTER_FILTER_MAX_PRICE` | Maximum price (euros) |
| `FLATHUNTER_FILTER_MIN_SIZE` | Minimum size (sqm) |
| `FLATHUNTER_FILTER_MAX_SIZE` | Maximum size (sqm) |
| `FLATHUNTER_FILTER_MIN_ROOMS` | Minimum rooms |
| `FLATHUNTER_FILTER_MAX_ROOMS` | Maximum rooms |

## Credits

Originally by [@NodyHub](https://github.com/NodyHub). Forked from [flathunters/flathunter](https://github.com/flathunters/flathunter).

ImmoScout24 mobile API reverse engineering thanks to the devs of [Fredy](https://github.com/orangecoding/fredy).
