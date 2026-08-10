# Sighetu Marmației bars & restaurants scraper

A beginner-friendly Python script that collects contact info (name,
address, phone, website, Google Maps link) for bars and restaurants in
Sighetu Marmației, Romania, using the Google Places API, and saves them to
`sighetu_bars_restaurants.xlsx`. The `Notes` column is left blank so you
can fill it in manually later (e.g. after calling around about draught
beer selection).

## 1. Get a Google Places API key

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

## 2. Set the `GOOGLE_PLACES_API_KEY` environment variable

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

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Run the script

```bash
python scrape_sighetu_bars_restaurants.py
```

This will create:
- `sighetu_bars_restaurants.xlsx` — the results
- `sighetu_scraper.log` — a log of anything that was skipped and why

## Notes on cost

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
