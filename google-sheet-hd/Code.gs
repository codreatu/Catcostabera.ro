/**
 * Bier in HD — public "Hinzufügen" write endpoint.
 *
 * Deploy steps (in the Google Sheet, not in this file's location):
 *   1. Open the spreadsheet -> Extensions -> Apps Script.
 *   2. Delete whatever's in the default Code.gs and paste this whole file in.
 *   3. Deploy -> New deployment -> pick type "Web app".
 *   4. Execute as: Me
 *      Who has access: Anyone
 *   5. Deploy, authorize when prompted, then copy the "Web app URL"
 *      (ends in /exec) and paste it into ADD_BAR_URL near the top of
 *      bier-in-hd.html's <script>.
 *
 * This runs with YOUR permissions (because "Execute as: Me"), so visitors
 * never need to sign in or have edit access themselves — the sharing
 * setting on the sheet doesn't matter for this path at all. If a
 * submission still isn't showing up, the deployment's "Who has access"
 * is almost always the culprit — it must be "Anyone", not "Anyone with
 * Google account".
 *
 * Sheet: https://docs.google.com/spreadsheets/d/1_eEvvCN4kQlhO298_McnxXi1IpFhj4gb42ZAXlCGKRc/edit?usp=sharing
 * Tab columns (row 1 = headers): A Name | B Stadtteil/Adresse | C Lat
 * | D Lng | E Öffnet (Std) | F Schließt (Std) | G Biere | H Tags
 */

const SHEET_ID = "1_eEvvCN4kQlhO298_McnxXi1IpFhj4gb42ZAXlCGKRc";
// gid pins the write to that exact tab (its numeric id, from the sheet's
// own URL — .../edit#gid=1658058362), matching what bier-in-hd.html reads.
// SHEET_NAME is only a fallback, in case the gid ever stops resolving.
const SHEET_GID = 1658058362;
const SHEET_NAME = "Bars";

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonOut({ ok: false, error: "Leere Anfrage." });
    }
    const data = JSON.parse(e.postData.contents);

    const sheet = getTargetSheet();
    if (!sheet) {
      return jsonOut({ ok: false, error: "Ziel-Tab nicht gefunden (gid " + SHEET_GID + ")." });
    }

    const name = clean(data.name);
    const neighborhood = clean(data.neighborhood);

    const lat = num(data.lat);
    const lng = num(data.lng);
    const openH = num(data.openHour);
    const closeH = num(data.closeHour);

    if (!name || lat === "" || lng === "" || openH === "" || closeH === "") {
      return jsonOut({ ok: false, error: "Fehlende Pflichtfelder (Name, Standort auf der Karte, Öffnungszeiten)." });
    }
    // Loose bounding box around Heidelberg — catches a stray pin dropped
    // way off (wrong country etc.) without being fussy about the edges.
    if (lat < 49.2 || lat > 49.6 || lng < 8.4 || lng > 9.0) {
      return jsonOut({ ok: false, error: "Koordinaten scheinen außerhalb von Heidelberg zu liegen — Pin auf der Karte prüfen." });
    }

    const beers = Array.isArray(data.beers) ? data.beers : [];
    const beerStr = beers.map(function (b) {
      const bn = clean(b && b.name);
      const bp = num(b && b.price);
      const bv = clean(b && b.volume);
      if (!bn || bp === "") return null;
      return bn + ":" + bp + ":" + bv;
    }).filter(function (x) { return x; }).join(" | ");

    if (!beerStr) {
      return jsonOut({ ok: false, error: "Mindestens ein Bier mit Namen und Preis nötig." });
    }

    const row = [
      name, neighborhood, lat, lng, openH, closeH,
      beerStr,
      "", // Tags leer — später direkt in der Tabelle editierbar
    ];
    sheet.appendRow(row);

    return jsonOut({ ok: true });
  } catch (err) {
    return jsonOut({ ok: false, error: String(err) });
  }
}

function doGet(e) {
  return jsonOut({ ok: true, message: "Bier in HD Apps Script läuft." });
}

function getTargetSheet() {
  const ss = SpreadsheetApp.openById(SHEET_ID);
  return ss.getSheetById(SHEET_GID) || ss.getSheetByName(SHEET_NAME);
}

// Guards against spreadsheet formula injection: a cell value starting with
// = + - or @ gets evaluated as a formula by Sheets. Prefixing with an
// apostrophe forces it to render as plain text instead.
function clean(v) {
  let s = (v === undefined || v === null) ? "" : String(v).trim();
  if (/^[=+\-@]/.test(s)) s = "'" + s;
  return s;
}
function num(v) {
  const n = Number(v);
  return isFinite(n) && v !== "" && v !== null && v !== undefined ? n : "";
}
function jsonOut(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
