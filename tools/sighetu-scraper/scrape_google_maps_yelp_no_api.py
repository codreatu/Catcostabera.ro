#!/usr/bin/env python3
"""
scrape_google_maps_yelp_no_api.py

Collects contact info (name, address, phone, website, Google Maps URL) for
bars/restaurants in Sighetu Marmatiei, Romania, by driving a real browser
(Playwright) against the public Google Maps and Yelp websites -- NO API key,
NO Google Cloud billing account required.

============================== READ THIS FIRST ==============================

1. This is fragile by nature. Unlike the official Places API, there is no
   stable contract here -- Google and Yelp can change their page markup at
   any time, which breaks the CSS/attribute selectors below. If a run comes
   back mostly empty, that's the most likely cause. Re-run with --debug to
   save a screenshot + HTML dump of the first failure into debug/ so you (or
   an LLM) can update the selectors.

2. Terms of Service: both Google Maps and Yelp prohibit automated scraping
   of their sites in their Terms of Service. This script is meant for
   small, occasional, personal research (looking up a few dozen businesses
   in one town) -- not for large-scale or repeated harvesting. Running it
   is at your own risk: expect CAPTCHAs, rate limiting, or a temporary IP
   block if you run it too often or too fast. If that matters for your use
   case, prefer the official-API version of this tool
   (scrape_sighetu_bars_restaurants.py in this same folder), which is the
   compliant way to get this data and is not materially more expensive for
   a single town.

3. Yelp's coverage of small Romanian towns is close to nonexistent -- don't
   be surprised if the Yelp portion returns zero results for Sighetu
   Marmatiei. It's included so the script is reusable for towns/areas where
   Yelp actually has listings.

4. NOT RUN END-TO-END BY THE ASSISTANT: this was written and reviewed, but
   could not be executed against the real sites from the environment it was
   written in (outbound access to google.com/yelp.com was blocked there).
   Please test it yourself and treat the first run as a trial.

===============================================================================

Setup:
    pip install -r requirements.txt
    playwright install chromium      # downloads the actual browser binary
    # Linux only, if playwright complains about missing system libraries:
    playwright install-deps chromium

Run:
    python scrape_google_maps_yelp_no_api.py
    python scrape_google_maps_yelp_no_api.py --headed --debug   # to watch it work / debug
"""

import argparse
import logging
import os
import random
import re
import sys
import time
import unicodedata
from datetime import datetime
from urllib.parse import quote

import pandas as pd

try:
    from playwright.sync_api import (
        sync_playwright,
        Page,
        TimeoutError as PlaywrightTimeoutError,
    )
except ImportError:
    print(
        "ERROR: playwright is not installed. Run:\n"
        "    pip install -r requirements.txt\n"
        "    playwright install chromium"
    )
    sys.exit(1)


# --------------------------------------------------------------------------
# CONFIGURATION - feel free to tweak these
# --------------------------------------------------------------------------

LOCATION = "Sighetu Marmatiei, Romania"

# Separate query lists per site because Google Maps and Yelp search syntax
# differs slightly (Yelp wants a "what" + "where" pair, not one free-text
# string).
GOOGLE_SEARCH_TERMS = ["bars", "restaurants", "pubs"]
YELP_SEARCH_TERMS = ["Bars", "Restaurants"]

OUTPUT_FILE = "sighetu_bars_restaurants_no_api.xlsx"
LOG_FILE = "sighetu_scraper_no_api.log"
DEBUG_DIR = "debug"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def polite_sleep(delay_min, delay_max):
    """Small random pause between page loads so we don't hammer the site."""
    time.sleep(random.uniform(delay_min, delay_max))


def save_debug(page: Page, stats, label: str, args):
    """On failure, save a screenshot + HTML so selectors can be fixed later."""
    if not args.debug:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    stats["debug_dumps"] += 1
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    base = os.path.join(DEBUG_DIR, f"{label}_{ts}")
    try:
        page.screenshot(path=base + ".png", full_page=True)
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(page.content())
        logging.info("  debug dump saved: %s.(png|html)", base)
    except Exception as exc:  # noqa: BLE001
        logging.warning("  could not save debug dump: %s", exc)


def normalize_name(name: str) -> str:
    """Lowercase + strip accents/punctuation, used only to flag possible
    duplicates between Google Maps and Yelp (same place, different site)."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_only.lower())


# --------------------------------------------------------------------------
# Google Maps
# --------------------------------------------------------------------------

def dismiss_google_consent(page: Page):
    """Google shows an EU cookie-consent screen on first visit. Click
    through it if present; do nothing if it isn't (already dismissed, or
    a region that doesn't show it)."""
    for text in ["Reject all", "Accept all", "I agree", "Alle ablehnen"]:
        try:
            btn = page.locator(f"button:has-text('{text}')").first
            if btn.count() and btn.is_visible():
                btn.click(timeout=3000)
                page.wait_for_timeout(800)
                return
        except Exception:  # noqa: BLE001
            continue


def _scroll_feed_to_bottom(page: Page, max_results, max_rounds=40):
    """Google Maps' left-hand results panel is a scrollable <div role="feed">
    that lazy-loads more listings as you scroll it. Keep scrolling until the
    listing count stops growing (end of list) or we have enough results."""
    feed_selector = 'div[role="feed"]'
    link_selector = f'{feed_selector} a[href^="https://www.google.com/maps/place"]'
    prev_count = -1
    stagnant_rounds = 0
    for _ in range(max_rounds):
        try:
            page.eval_on_selector(feed_selector, "el => el.scrollTop = el.scrollHeight")
        except Exception:  # noqa: BLE001
            break
        page.wait_for_timeout(1500)
        count = page.locator(link_selector).count()
        if max_results and count >= max_results:
            break
        if count == prev_count:
            stagnant_rounds += 1
            if stagnant_rounds >= 3:
                break
        else:
            stagnant_rounds = 0
        prev_count = count


def _extract_place_key(href: str) -> str:
    """Pull the stable per-place ID out of a Google Maps place URL so we can
    deduplicate. Falls back to the raw URL if the pattern isn't found."""
    match = re.search(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", href or "")
    return match.group(1) if match else (href or "")


def google_maps_collect_listings(page: Page, query, location, max_results, stats, args):
    """Run one Google Maps search and return a list of {name, href} dicts
    for each unique business found (not yet fetching phone/website)."""
    full_query = f"{query} in {location}"
    url = f"https://www.google.com/maps/search/{quote(full_query)}?hl=en&gl=ro"
    logging.info("Google Maps: searching '%s'", full_query)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        stats["google_pages_loaded"] += 1
    except Exception as exc:  # noqa: BLE001
        logging.error("Google Maps: failed to load search '%s': %s", full_query, exc)
        return []

    dismiss_google_consent(page)
    page.wait_for_timeout(1500)

    # Edge case: if the query matches a single business, Google may jump
    # straight to its place page instead of showing a list.
    if "/maps/place/" in page.url:
        name = _first_text(page, "h1")
        return [{"name": name, "href": page.url}]

    try:
        page.wait_for_selector('div[role="feed"]', timeout=15000)
    except PlaywrightTimeoutError:
        logging.warning("Google Maps: no results feed for '%s' (likely zero results).", full_query)
        save_debug(page, stats, "google_no_feed", args)
        return []

    _scroll_feed_to_bottom(page, max_results)

    anchors = page.locator('div[role="feed"] a[href^="https://www.google.com/maps/place"]')
    count = anchors.count()
    listings = []
    seen_keys = set()
    for i in range(count):
        a = anchors.nth(i)
        try:
            href = a.get_attribute("href")
            name = a.get_attribute("aria-label") or ""
        except Exception:  # noqa: BLE001
            continue
        if not href:
            continue
        key = _extract_place_key(href)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        listings.append({"name": name, "href": href})
        if max_results and len(listings) >= max_results:
            break

    logging.info("Google Maps: '%s' -> %d unique listings", full_query, len(listings))
    return listings


def _first_text(page: Page, selector: str) -> str:
    try:
        el = page.locator(selector).first
        if el.count():
            return (el.inner_text() or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _get_item_text(page: Page, item_id: str) -> str:
    """Read an info-panel field (address, website label, etc.) via its
    data-item-id attribute, using the aria-label (e.g. 'Address: Str. X')
    since that's more stable than Google's obfuscated CSS class names."""
    try:
        btn = page.locator(f'button[data-item-id="{item_id}"]').first
        if not btn.count():
            return ""
        aria = btn.get_attribute("aria-label") or ""
        if ":" in aria:
            return aria.split(":", 1)[1].strip()
        return aria.strip()
    except Exception:  # noqa: BLE001
        return ""


def _get_phone(page: Page) -> str:
    """Phone buttons have data-item-id="phone:tel:+40...", so the number is
    right there in the attribute -- no locale-dependent text parsing needed."""
    try:
        btn = page.locator('button[data-item-id^="phone:tel:"]').first
        if not btn.count():
            return ""
        item_id = btn.get_attribute("data-item-id") or ""
        prefix = "phone:tel:"
        if item_id.startswith(prefix):
            return item_id[len(prefix):]
        aria = btn.get_attribute("aria-label") or ""
        return aria.split(":", 1)[1].strip() if ":" in aria else aria
    except Exception:  # noqa: BLE001
        return ""


def _get_website(page: Page) -> str:
    try:
        link = page.locator('a[data-item-id="authority"]').first
        if link.count():
            href = link.get_attribute("href")
            if href:
                return href
    except Exception:  # noqa: BLE001
        pass
    return ""


def google_maps_fetch_details(page: Page, href: str, stats, args):
    """Open one business's Google Maps page and read name/address/phone/
    website/URL out of the info panel. Raises on a real failure; the caller
    decides to skip-and-log rather than crash the whole run."""
    page.goto(href, wait_until="domcontentloaded", timeout=30000)
    stats["google_pages_loaded"] += 1
    dismiss_google_consent(page)
    page.wait_for_selector("h1", timeout=15000)
    page.wait_for_timeout(700)  # let the info panel finish rendering

    name = _first_text(page, "h1")
    if not name:
        raise RuntimeError("could not find a business name (h1) on the page")

    return {
        "Name": name,
        "Address": _get_item_text(page, "address"),
        "Phone": _get_phone(page),
        "Website": _get_website(page),
        "Google Maps URL": page.url,
        "Source": "Google Maps",
        "Notes": "",
    }


# --------------------------------------------------------------------------
# Yelp
# --------------------------------------------------------------------------

def dismiss_yelp_consent(page: Page):
    for text in ["OK", "Accept", "I Accept", "Got it", "Accept All"]:
        try:
            btn = page.locator(f"button:has-text('{text}')").first
            if btn.count() and btn.is_visible():
                btn.click(timeout=3000)
                page.wait_for_timeout(500)
                return
        except Exception:  # noqa: BLE001
            continue


def yelp_collect_listings(page: Page, term, location, max_results, stats, args):
    """Search Yelp and return {name, href} dicts, paging through results
    10-at-a-time (Yelp's default page size) until we run out or hit
    max_results."""
    listings = []
    seen_paths = set()
    start = 0
    page_size = 10
    max_pages = 6  # safety cap: 60 results per term is plenty for one town

    for page_num in range(max_pages):
        url = (
            f"https://www.yelp.com/search?find_desc={quote(term)}"
            f"&find_loc={quote(location)}&start={start}"
        )
        logging.info("Yelp: searching '%s' (page %d)", term, page_num + 1)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            stats["yelp_pages_loaded"] += 1
        except Exception as exc:  # noqa: BLE001
            logging.error("Yelp: failed to load search '%s': %s", term, exc)
            break

        dismiss_yelp_consent(page)
        page.wait_for_timeout(1500)

        body_text = _first_text(page, "body")
        if re.search(r"No results found", body_text, re.IGNORECASE):
            logging.info("Yelp: '%s' -> no results (page %d)", term, page_num + 1)
            break

        anchors = page.locator('a[href^="/biz/"]')
        count = anchors.count()
        new_this_page = 0
        for i in range(count):
            a = anchors.nth(i)
            try:
                href = a.get_attribute("href") or ""
                name = (a.inner_text() or "").strip()
            except Exception:  # noqa: BLE001
                continue
            path = href.split("?")[0]
            if not path or path in seen_paths or not name:
                continue
            seen_paths.add(path)
            listings.append({"name": name, "href": "https://www.yelp.com" + path})
            new_this_page += 1
            if max_results and len(listings) >= max_results:
                break

        if max_results and len(listings) >= max_results:
            break
        if new_this_page == 0:
            break  # no new businesses on this page -> end of results

        start += page_size
        polite_sleep(args.delay_min, args.delay_max)

    logging.info("Yelp: '%s' -> %d unique listings", term, len(listings))
    return listings


def yelp_fetch_details(page: Page, href: str, stats, args):
    page.goto(href, wait_until="domcontentloaded", timeout=30000)
    stats["yelp_pages_loaded"] += 1
    dismiss_yelp_consent(page)
    page.wait_for_selector("h1", timeout=15000)
    page.wait_for_timeout(500)

    name = _first_text(page, "h1")
    if not name:
        raise RuntimeError("could not find a business name (h1) on the page")

    address = ""
    addr_el = page.locator("address").first
    if addr_el.count():
        address = re.sub(r"\s*\n\s*", ", ", addr_el.inner_text().strip())

    phone = ""
    body_text = _first_text(page, "body")
    m = re.search(r"Phone number\s*\n?\s*([+0-9][0-9()\s.+-]{6,}[0-9])", body_text)
    if m:
        phone = m.group(1).strip()

    # Yelp doesn't publish the raw website URL -- clicking "Business website"
    # goes through a Yelp redirect link (yelp.com/biz_redir?...). We capture
    # that redirect link as-is rather than following it (following it would
    # be an extra request per business, and the redirect link still gets you
    # to the site if you open it in a browser).
    website = ""
    web_link = page.locator('a[href*="biz_redir"]').first
    if web_link.count():
        website = web_link.get_attribute("href") or ""

    return {
        "Name": name,
        "Address": address,
        "Phone": phone,
        "Website": website,
        "Google Maps URL": "",  # Yelp doesn't provide a Google Maps link
        "Source": "Yelp",
        "Notes": "",
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--location", default=LOCATION, help="Town/area to search (default: %(default)s)")
    p.add_argument("--output", default=OUTPUT_FILE, help="Output .xlsx path")
    p.add_argument("--skip-google", action="store_true", help="Don't scrape Google Maps")
    p.add_argument("--skip-yelp", action="store_true", help="Don't scrape Yelp")
    p.add_argument("--max-per-query", type=int, default=None, help="Cap results per search term (default: no cap)")
    p.add_argument("--headed", action="store_true", help="Show the browser window instead of running headless")
    p.add_argument("--debug", action="store_true", help="Save screenshots/HTML to debug/ when something fails")
    p.add_argument("--delay-min", type=float, default=1.5, help="Minimum seconds to wait between page loads")
    p.add_argument("--delay-max", type=float, default=3.5, help="Maximum seconds to wait between page loads")
    return p.parse_args()


def annotate_possible_duplicates(rows):
    """Best-effort flag (not a silent merge) for the same business appearing
    under both Google Maps and Yelp: same normalized name, different
    source. Doesn't touch rows that are only duplicated within one source
    (those are already deduped by place key / biz path)."""
    groups = {}
    for idx, row in enumerate(rows):
        key = normalize_name(row["Name"])
        if not key:
            continue
        groups.setdefault(key, []).append(idx)

    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        sources = {rows[i]["Source"] for i in idxs}
        if len(sources) < 2:
            continue
        for i in idxs:
            note = f"Possible duplicate across sources ({'/'.join(sorted(sources))}) - verify before contacting."
            rows[i]["Notes"] = (rows[i]["Notes"] + " " if rows[i]["Notes"] else "") + note


def main():
    args = parse_args()
    setup_logging()

    stats = {
        "google_pages_loaded": 0,
        "yelp_pages_loaded": 0,
        "businesses_saved": 0,
        "businesses_failed": 0,
        "debug_dumps": 0,
    }
    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            timezone_id="Europe/Bucharest",
        )
        page = context.new_page()

        # ---------------- Google Maps ----------------
        if not args.skip_google:
            google_listings = []
            seen_keys = set()
            for term in GOOGLE_SEARCH_TERMS:
                found = google_maps_collect_listings(
                    page, term, args.location, args.max_per_query, stats, args
                )
                for item in found:
                    key = _extract_place_key(item["href"])
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    google_listings.append(item)
                polite_sleep(args.delay_min, args.delay_max)

            logging.info("Google Maps: %d unique businesses total across all search terms", len(google_listings))
            for item in google_listings:
                try:
                    details = google_maps_fetch_details(page, item["href"], stats, args)
                    rows.append(details)
                    stats["businesses_saved"] += 1
                except Exception as exc:  # noqa: BLE001
                    logging.warning(
                        "Google Maps: skipping '%s': %s", item.get("name", "<unknown>"), exc
                    )
                    save_debug(page, stats, "google_detail_fail", args)
                    stats["businesses_failed"] += 1
                polite_sleep(args.delay_min, args.delay_max)

        # ---------------- Yelp ----------------
        if not args.skip_yelp:
            yelp_listings = []
            seen_paths = set()
            for term in YELP_SEARCH_TERMS:
                found = yelp_collect_listings(page, term, args.location, args.max_per_query, stats, args)
                for item in found:
                    path = item["href"]
                    if path in seen_paths:
                        continue
                    seen_paths.add(path)
                    yelp_listings.append(item)
                polite_sleep(args.delay_min, args.delay_max)

            logging.info("Yelp: %d unique businesses total across all search terms", len(yelp_listings))
            for item in yelp_listings:
                try:
                    details = yelp_fetch_details(page, item["href"], stats, args)
                    rows.append(details)
                    stats["businesses_saved"] += 1
                except Exception as exc:  # noqa: BLE001
                    logging.warning("Yelp: skipping '%s': %s", item.get("name", "<unknown>"), exc)
                    save_debug(page, stats, "yelp_detail_fail", args)
                    stats["businesses_failed"] += 1
                polite_sleep(args.delay_min, args.delay_max)

        browser.close()

    annotate_possible_duplicates(rows)

    df = pd.DataFrame(
        rows,
        columns=["Name", "Address", "Phone", "Website", "Google Maps URL", "Source", "Notes"],
    )
    df.to_excel(args.output, index=False)

    total_pages = stats["google_pages_loaded"] + stats["yelp_pages_loaded"]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Businesses saved to file:   {stats['businesses_saved']}")
    print(f"Businesses skipped (error): {stats['businesses_failed']}")
    print(f"Google Maps pages loaded:   {stats['google_pages_loaded']}")
    print(f"Yelp pages loaded:          {stats['yelp_pages_loaded']}")
    print(f"Total pages loaded:         {total_pages}")
    print("Estimated cost:             $0 (no API used - just browser automation)")
    if stats["debug_dumps"]:
        print(f"Debug dumps saved:          {stats['debug_dumps']} (see {DEBUG_DIR}/)")
    print(f"Output file:                {os.path.abspath(args.output)}")
    print(f"Log file:                   {os.path.abspath(LOG_FILE)}")
    print("=" * 60)
    print(f"Run finished at {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
