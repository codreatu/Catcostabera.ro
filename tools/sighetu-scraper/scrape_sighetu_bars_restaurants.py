#!/usr/bin/env python3
"""
scrape_sighetu_bars_restaurants.py

Collects contact info (name, address, phone, website, Google Maps URL) for
bars and restaurants in Sighetu Marmatiei, Romania, using the Google Places
API, and saves the results to an Excel file.

WHY TWO API CALLS PER BUSINESS?
--------------------------------
Google's (classic/legacy) Places API bills by "data tier":
  - Text Search always returns a flat set of "Basic Data" fields (name,
    address, place_id, ...) for one price per request. It does NOT let you
    ask for phone numbers or websites.
  - Place Details lets you ask for exactly the fields you want via the
    `fields` parameter. Fields are grouped into tiers:
        Basic Data      -> name, formatted_address, url (Maps link)   (cheapest)
        Contact Data    -> international_phone_number, website       (paid)
        Atmosphere Data -> rating, reviews, photos, price_level       (most expensive)
  So: we run Text Search once per search term (e.g. "bars in ..."), then for
  each unique place found we run ONE Place Details call asking ONLY for
  Basic + Contact fields. We never ask for Atmosphere Data, which is the
  main way this script keeps costs down.

See the accompanying README.md for how to get an API key and set the
GOOGLE_PLACES_API_KEY environment variable before running this script.
"""

import os
import sys
import time
import logging
from datetime import datetime

import requests
import pandas as pd

# --------------------------------------------------------------------------
# CONFIGURATION - feel free to tweak these
# --------------------------------------------------------------------------

# One Text Search query is run per term below. Using both "bar" and
# "restaurant" (and a couple of synonyms) casts a wider net than a single
# query, at the cost of some overlap -- which we remove later (step 4).
SEARCH_TERMS = [
    "bars in Sighetu Marmatiei, Romania",
    "restaurants in Sighetu Marmatiei, Romania",
    "pubs in Sighetu Marmatiei, Romania",
]

OUTPUT_FILE = "sighetu_bars_restaurants.xlsx"
LOG_FILE = "sighetu_scraper.log"

# Fields requested from the Place Details endpoint. Keep this list short --
# every extra field can push you into a more expensive pricing tier.
#   name, formatted_address, url  -> Basic Data (cheap)
#   international_phone_number,
#   website                        -> Contact Data (paid, but no way around
#                                      it if we want phone/website)
# Deliberately NOT requesting: rating, user_ratings_total, reviews, photos,
# opening_hours, price_level (Atmosphere Data -- the expensive tier).
DETAILS_FIELDS = "name,formatted_address,international_phone_number,website,url"

# --------------------------------------------------------------------------
# COST ESTIMATION (approximate!)
# --------------------------------------------------------------------------
# Google's pricing changes over time and depends on your account/region, so
# treat these as rough placeholders, NOT a guarantee. Before relying on this
# number, check the current prices at:
#   https://developers.google.com/maps/billing-and-pricing/pricing
# and update the two constants below to match.
TEXT_SEARCH_COST_PER_CALL_USD = 0.032   # Text Search, Basic Data
DETAILS_COST_PER_CALL_USD = 0.003       # Place Details, Basic + Contact Data

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

REQUEST_TIMEOUT_SECONDS = 15


def setup_logging():
    """Send log messages to both the console and a log file."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def get_api_key():
    """Read the API key from the environment. Never hardcode it in code!"""
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print(
            "ERROR: The GOOGLE_PLACES_API_KEY environment variable is not set.\n"
            "See README.md in this folder for instructions on getting a key\n"
            "and setting the environment variable, then try again."
        )
        sys.exit(1)
    return api_key


def text_search(query, api_key, session, stats):
    """
    Run a Google Places Text Search for `query`, following pagination
    (Google returns at most 20 results per page, up to 60 total, and gives
    you a `next_page_token` to fetch the next page).

    Returns a list of raw result dicts (each has at least 'place_id' and
    'name').
    """
    results = []
    params = {"query": query, "key": api_key}

    while True:
        try:
            response = session.get(
                TEXT_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
            )
            stats["text_search_calls"] += 1
            data = response.json()
        except requests.exceptions.RequestException as exc:
            logging.error("Text Search request failed for query '%s': %s", query, exc)
            break

        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            logging.error(
                "Text Search returned status '%s' for query '%s': %s",
                status,
                query,
                data.get("error_message", ""),
            )
            break

        results.extend(data.get("results", []))

        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break  # no more pages

        # Google requires a short delay before a next_page_token becomes
        # usable -- calling too soon returns INVALID_REQUEST.
        time.sleep(2)
        params = {"pagetoken": next_page_token, "key": api_key}

    return results


def get_place_details(place_id, api_key, session, stats):
    """
    Fetch only the fields we need (see DETAILS_FIELDS) for one place_id.
    Raises an exception on failure -- the caller decides what to do (we
    skip and log the business rather than crashing the whole run).
    """
    params = {"place_id": place_id, "fields": DETAILS_FIELDS, "key": api_key}
    response = session.get(DETAILS_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    stats["details_calls"] += 1
    data = response.json()

    if data.get("status") != "OK":
        raise RuntimeError(
            f"status={data.get('status')} message={data.get('error_message', '')}"
        )

    return data["result"]


def main():
    setup_logging()
    api_key = get_api_key()

    session = requests.Session()

    # Simple counters used for the end-of-run summary.
    stats = {
        "text_search_calls": 0,
        "details_calls": 0,
        "failed_businesses": 0,
    }

    seen_place_ids = set()  # used to deduplicate across search terms
    rows = []

    for term in SEARCH_TERMS:
        logging.info("Searching: %s", term)
        results = text_search(term, api_key, session, stats)
        logging.info("  -> %d raw results", len(results))

        for result in results:
            place_id = result.get("place_id")
            name_hint = result.get("name", "<unknown>")

            if not place_id:
                logging.warning("Skipping a result with no place_id: %s", name_hint)
                continue

            # Deduplicate: the same place can show up under both "bar" and
            # "restaurant" searches.
            if place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)

            try:
                details = get_place_details(place_id, api_key, session, stats)
            except Exception as exc:  # noqa: BLE001 - we want to catch anything
                # Don't let one bad business kill the whole run: log and move on.
                logging.warning(
                    "Skipping '%s' (place_id=%s): failed to fetch details: %s",
                    name_hint,
                    place_id,
                    exc,
                )
                stats["failed_businesses"] += 1
                continue

            rows.append(
                {
                    "Name": details.get("name", ""),
                    "Address": details.get("formatted_address", ""),
                    "Phone": details.get("international_phone_number", ""),
                    "Website": details.get("website", ""),
                    "Google Maps URL": details.get("url", ""),
                    "Notes": "",  # left blank for manual follow-up
                }
            )

    # Save to Excel. `columns=` fixes the column order even if `rows` is empty.
    df = pd.DataFrame(
        rows, columns=["Name", "Address", "Phone", "Website", "Google Maps URL", "Notes"]
    )
    df.to_excel(OUTPUT_FILE, index=False)

    # --------------------------------------------------------------------
    # Summary
    # --------------------------------------------------------------------
    total_calls = stats["text_search_calls"] + stats["details_calls"]
    estimated_cost = (
        stats["text_search_calls"] * TEXT_SEARCH_COST_PER_CALL_USD
        + stats["details_calls"] * DETAILS_COST_PER_CALL_USD
    )

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Businesses saved to file:   {len(rows)}")
    print(f"Businesses skipped (error): {stats['failed_businesses']}")
    print(f"Text Search API calls:      {stats['text_search_calls']}")
    print(f"Place Details API calls:    {stats['details_calls']}")
    print(f"Total API calls:            {total_calls}")
    print(f"Estimated cost (USD):       ${estimated_cost:.2f}  (rough estimate, see script comments)")
    print(f"Output file:                {os.path.abspath(OUTPUT_FILE)}")
    print(f"Log file:                   {os.path.abspath(LOG_FILE)}")
    print("=" * 60)
    print(f"Run finished at {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
