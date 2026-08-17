# Bier in HD — Google Sheet + Apps Script

Database backend for `bier-in-hd.html`, the Heidelberg-only test variant of
Cât Costă Berea?. Single city, no happy-hour data, prices in euro.

## Files

- **`Bier-in-HD-Bars.xlsx`** — spreadsheet template. Tab `Bars` is the live
  database (8 demo rows matching the page's offline fallback); tab
  `Anleitung` documents the columns, the price-tier colors, and includes a
  small conditionally-formatted example.
- **`Code.gs`** — Apps Script web app that receives "+ Hinzufügen" form
  submissions and appends a row to the `Bars` tab.

## Setup

1. **Create the live sheet.** In Google Drive: Upload `Bier-in-HD-Bars.xlsx`,
   then open it with Google Sheets (this converts it to a native Sheet) —
   or create a blank Google Sheet and use File > Import > Upload instead.
2. **Rename the file** to whatever you like; just keep the tab named
   exactly `Bars` (the page reads `sheet=Bars` from the gviz endpoint).
3. **Share it**: Share > General access > "Anyone with the link" → Viewer.
   This lets the page read it without any login.
4. **Copy the Sheet ID** from the URL (`.../d/<SHEET_ID>/edit`) into the
   `SHEET_ID` constant near the top of `bier-in-hd.html`.
5. **Add the script**: Extensions > Apps Script, replace the default
   content with `Code.gs`, save.
6. **Deploy**: Deploy > New deployment > type "Web app" → Execute as **Me**,
   who has access **Anyone**. Copy the `/exec` URL.
7. Paste that URL into `ADD_BAR_URL` in `bier-in-hd.html`.

Once both `SHEET_ID` and `ADD_BAR_URL` are filled in, the page reads bars
live from the sheet, and the "+ Hinzufügen" form writes new submissions
straight back into it.

## Price color rule (matches the map markers)

- 🟢 Green — under 3,00 €
- 🟡 Yellow — 3,00 € to 5,00 €
- 🔴 Red — over 5,00 €

This is computed by the page from each beer's price (packed into the
`Biere` column as `Name:Preis:Volumen`), not by spreadsheet cell color —
the `Anleitung` tab's example table only illustrates the same thresholds.
