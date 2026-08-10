# Sighetu Marmației bars & restaurants scraper

Two scripts that collect contact info (name, address, phone, website,
Google Maps link) for bars and restaurants in Sighetu Marmației, Romania,
and save it to an `.xlsx` file with a blank `Notes` column for you to fill
in manually later (e.g. draught beer info from outreach calls).

| | `scrape_sighetu_bars_restaurants.py` | `scrape_google_maps_yelp_no_api.py` |
|---|---|---|
| Data source | Official Google Places API | Google Maps + Yelp web pages, via headless browser |
| Needs | API key + billing account | Nothing but Python + Playwright |
| Cost | A few dollars for one town (see below) | $0, but breaks ToS (see below) |
| Reliability | Stable, documented contract | Breaks whenever Google/Yelp change their HTML |

**Recommendation:** use `scrape_sighetu_bars_restaurants.py` if you can —
it's the compliant, stable option and isn't meaningfully more expensive for
one town's worth of data. Use `scrape_google_maps_yelp_no_api.py` if you'd
rather not set up billing at all.

---

## Option A: Official API (`scrape_sighetu_bars_restaurants.py`)

### 1. Get a Google Places API key

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or pick an existing one) from the project
   dropdown at the top of the page.
3. **Enable billing** for the project. Google requires a linked billing
   account even though new accounts get a recurring free credit
   (currently ~$200/month) — this script's usage should stay well within
   that for a single town's worth of businesses, but see the cost note
   below.
4. Go to **APIs & Services → Library**, search for **"Places API"**, and
   click **Enable**. (This script uses the classic/legacy Places API —
   make sure it's "Places API", not only "Places API (New)".)
5. Go to **APIs & Services → Credentials → Create Credentials → API key**.
   Copy the key that's generated.
6. (Strongly recommended) Click on the new key and restrict it:
   - Under **API restrictions**, choose "Restrict key" and select just
     **Places API**.
   - Under **Application restrictions**, you can restrict it to your IP
     address if you're only ever running this from one machine.
   This limits the damage if the key ever leaks.

### 2. Set the `GOOGLE_PLACES_API_KEY` environment variable

Never paste your key into the script. Instead, set it as an environment
variable in the terminal session you'll run the script from.

**macOS / Linux (bash/zsh):**
```bash
export GOOGLE_PLACES_API_KEY="your-key-here"
```
Add that line to your `~/.bashrc` / `~/.zshrc` if you want it to persist
across terminal sessions.

**Windows (PowerShell):**
```powershell
$env:GOOGLE_PLACES_API_KEY = "your-key-here"
```

**Windows (Command Prompt):**
```cmd
set GOOGLE_PLACES_API_KEY=your-key-here
```

These commands only set the variable for the current terminal window. Set
it again each time you open a new terminal (or add it to your shell's
startup file / Windows environment variables for something permanent).

### 3. Install dependencies and run

```bash
pip install -r requirements.txt
python scrape_sighetu_bars_restaurants.py
```

This will create:
- `sighetu_bars_restaurants.xlsx` — the results
- `sighetu_scraper.log` — a log of anything that was skipped and why

### Notes on cost

This script tries to keep API usage cheap:
- It only requests the specific fields it needs (name, address, phone,
  website, Maps URL) — never photos, reviews, or ratings, which fall into
  a more expensive Google pricing tier ("Atmosphere Data").
- It deduplicates places found across multiple search terms so each
  business only gets **one** Place Details call.

That said, Google's pricing changes over time. Before running this at
scale, check current prices at
https://developers.google.com/maps/billing-and-pricing/pricing and adjust
`TEXT_SEARCH_COST_PER_CALL_USD` / `DETAILS_COST_PER_CALL_USD` near the top
of the script if you want a more accurate cost estimate in the summary.
For a single town like Sighetu Marmației (a few dozen bars/restaurants),
expect on the order of a few dollars at most.

---

## Option B: No API, browser scraping (`scrape_google_maps_yelp_no_api.py`)

This drives a real (headless) Chromium browser against the public Google
Maps and Yelp websites with [Playwright](https://playwright.dev/python/),
reading data straight off the rendered page. No API key, no billing
account.

### Read this before using it

- **Terms of Service.** Both Google Maps and Yelp prohibit automated
  scraping in their ToS. This is meant for small, occasional, personal
  lookups (a few dozen businesses in one town) — not for repeated or
  large-scale harvesting. Running it is at your own risk: Google/Yelp may
  show CAPTCHAs, rate-limit you, or temporarily block your IP if you run
  it too often or too aggressively. If that risk matters for your
  situation, use Option A instead.
- **Fragility.** There's no stable contract here like there is with an
  API — Google/Yelp can and do change their page markup, which will break
  the selectors in this script sooner or later. If a run comes back mostly
  empty, that's the most likely cause. Run with `--debug` to save a
  screenshot + HTML dump of the failing page into `debug/`, which is the
  starting point for updating the selectors.
- **Yelp coverage in Romania is sparse to nonexistent**, especially for a
  small town like Sighetu Marmației. Don't be surprised if the Yelp half
  of the output is empty — that's expected, not a bug. It's there so the
  script is reusable elsewhere.
- **This script was written and reviewed, but the assistant could not run
  it end-to-end against the real sites** (outbound access to
  google.com/yelp.com was blocked in the environment it was built in).
  Its internal parsing logic was unit-tested against sample HTML matching
  Google/Yelp's known page structure, but **treat your first real run as a
  trial** — check the output file looks sane, and check `debug/` if it
  comes back empty.

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
# Linux only, if Playwright complains about missing system libraries:
playwright install-deps chromium
```

### 2. Run

```bash
python scrape_google_maps_yelp_no_api.py
```

Useful flags:
```bash
# Watch it work in a real browser window instead of headless (great for
# a first run / debugging):
python scrape_google_maps_yelp_no_api.py --headed

# Save a screenshot + HTML whenever something fails to parse:
python scrape_google_maps_yelp_no_api.py --debug

# Only do Google Maps, or only Yelp:
python scrape_google_maps_yelp_no_api.py --skip-yelp
python scrape_google_maps_yelp_no_api.py --skip-google

# Slow it down further (be gentler on the sites):
python scrape_google_maps_yelp_no_api.py --delay-min 3 --delay-max 6

# Reuse it for a different town:
python scrape_google_maps_yelp_no_api.py --location "Baia Mare, Romania"
```

This will create:
- `sighetu_bars_restaurants_no_api.xlsx` — the results, with an extra
  `Source` column (`Google Maps` or `Yelp`) since there's no shared place
  ID to dedupe across the two sites. Rows that look like the same business
  on both sites get a note in `Notes` flagging the possible duplicate —
  it's a heuristic (matches on business name), not guaranteed correct, so
  double-check before deleting either row.
- `sighetu_scraper_no_api.log` — a log of anything that was skipped and why
- `debug/*.png` / `debug/*.html` — only created with `--debug`, when a
  page fails to parse
