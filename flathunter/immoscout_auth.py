"""Auto-login to ImmoScout24 via stealth Playwright to refresh session cookies"""
from flathunter.logging import logger

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}};
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({state: Notification.permission}) :
    originalQuery(parameters)
);
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'de']});
"""


def refresh_immoscout_cookies(email: str, password: str, **_kwargs) -> str | None:
    """Log into ImmoScout24 via headless stealth browser and return cookie string."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("playwright not installed — cannot auto-refresh cookies")
        return None

    logger.info("ImmoScout: auto-refreshing cookies via stealth browser login")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="de-DE",
        )
        context.add_init_script(STEALTH_JS)
        page = context.new_page()

        try:
            page.goto(
                "https://www.immobilienscout24.de/geschlossenerbereich/start.html",
                wait_until="networkidle", timeout=30000,
            )

            # If WAF still triggers, bail
            if "Roboter" in (page.title() or ""):
                logger.error("ImmoScout: WAF captcha still triggered with stealth")
                browser.close()
                return None

            # Remove cookie consent overlay
            page.evaluate("() => document.querySelector('#usercentrics-root')?.remove()")

            # Step 1: email
            page.wait_for_selector("#username", timeout=15000)
            page.fill("#username", email)
            page.click("#submit", force=True)
            logger.debug("ImmoScout login: email submitted")

            # Step 2: password
            page.wait_for_selector("#password", timeout=15000)
            page.fill("#password", password)

            # Tick "remember me"
            try:
                cb = page.locator("#rememberMeCheckBox")
                if not cb.is_checked():
                    page.locator("label[for='rememberMeCheckBox']").click()
            except Exception:
                pass

            page.click("#loginOrRegistration", force=True)
            logger.debug("ImmoScout login: password submitted")

            # Wait for redirect to IS24 dashboard
            page.wait_for_timeout(5000)
            if "immobilienscout24.de" not in page.url:
                page.wait_for_url("**/immobilienscout24.de/**", timeout=25000)

            # Extract cookies
            cookies = context.cookies(["https://www.immobilienscout24.de"])
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
            logger.info("ImmoScout: login OK, got %d cookies", len(cookies))

            browser.close()
            return cookie_str

        except Exception as exc:
            logger.error("ImmoScout: auto-login failed: %s", exc)
            try:
                page.screenshot(path="/tmp/is24_login_debug.png")
                logger.info("Debug screenshot at /tmp/is24_login_debug.png, URL: %s", page.url)
            except Exception:
                pass
            browser.close()
            return None
