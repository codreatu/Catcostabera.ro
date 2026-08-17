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

## Live sheet

`bier-in-hd.html` is already wired to this sheet:

https://docs.google.com/spreadsheets/d/1_eEvvCN4kQlhO298_McnxXi1IpFhj4gb42ZAXlCGKRc/edit#gid=1658058362

The page reads that exact tab by its **gid** (`1658058362`), not by name, so
renaming the tab or adding others (e.g. an `Anleitung` tab) won't break it.
`Bier-in-HD-Bars.xlsx` is the template this sheet should match — use it as a
reference for column layout, or import it wholesale if the sheet is still
empty (File > Import > Upload, "Insert new sheet(s)").

## Setup

1. **Match the column layout.** The target tab (gid `1658058362`) needs the
   8 columns from `Bier-in-HD-Bars.xlsx`'s `Bars` tab, in order: Name,
   Stadtteil/Adresse, Lat, Lng, Öffnet (Std), Schließt (Std), Biere, Tags —
   row 1 = headers, data from row 2.
2. **Share it**: Share > General access > "Anyone with the link" → Viewer.
   This lets the page read it without any login.
3. **Add the script**: Extensions > Apps Script (from within that sheet, or
   standalone), replace the default content with `Code.gs`, save. It's
   already pointed at this sheet ID and gid, so no further edits needed.
4. **Deploy**: Deploy > New deployment > type "Web app" → Execute as **Me**,
   who has access **Anyone**. Copy the `/exec` URL.
5. Paste that URL into `ADD_BAR_URL` near the top of `bier-in-hd.html`
   (`SHEET_ID`/`SHEET_GID` there are already set).

Once `ADD_BAR_URL` is filled in, the page reads bars live from the sheet,
and the "+ Hinzufügen" form writes new submissions straight back into it.

## Price color rule (matches the map markers)

- 🟢 Green — under 3,00 €
- 🟡 Yellow — 3,00 € to 5,00 €
- 🔴 Red — over 5,00 €

This is computed by the page from each beer's price (packed into the
`Biere` column as `Name:Preis:Volumen`), not by spreadsheet cell color —
the `Anleitung` tab's example table only illustrates the same thresholds.
