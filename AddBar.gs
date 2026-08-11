/**
 * Cât Costă Berea? — public "Adaugă bar" write endpoint.
 *
 * Deploy steps (in the Google Sheet, not in this file's location):
 *   1. Open the spreadsheet -> Extensions -> Apps Script.
 *   2. Delete whatever's in the default Code.gs and paste this whole file in.
 *   3. Deploy -> New deployment -> pick type "Web app".
 *   4. Execute as: Me
 *      Who has access: Anyone
 *   5. Deploy, authorize when prompted, then copy the "Web app URL"
 *      (ends in /exec) and paste it into ADD_BAR_URL near the top of
 *      index.html's <script>.
 *
 * This runs with YOUR permissions (because "Execute as: Me"), so visitors
 * never need to sign in or have edit access themselves — the sharing
 * setting on the sheet doesn't matter for this path at all.
 */

const SHEET_NAME = "Baruri";

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonOut({ ok: false, error: "Cerere goală." });
    }
    const data = JSON.parse(e.postData.contents);

    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
    if (!sheet) {
      return jsonOut({ ok: false, error: "Nu găsesc tab-ul '" + SHEET_NAME + "'." });
    }

    const city = clean(data.city);
    const name = clean(data.name);
    let address = clean(data.address);
    const neighborhood = clean(data.neighborhood);
    if (neighborhood) address = address ? (address + ", " + neighborhood) : neighborhood;

    const lat = num(data.lat);
    const lng = num(data.lng);
    const openH = num(data.openHour);
    const closeH = num(data.closeHour);

    if (!city || !name || lat === "" || lng === "" || openH === "" || closeH === "") {
      return jsonOut({ ok: false, error: "Lipsesc câmpuri obligatorii (oraș, nume, locație pe hartă, program)." });
    }
    if (lat < 40 || lat > 52 || lng < 18 || lng > 32) {
      return jsonOut({ ok: false, error: "Coordonatele par în afara României — verifică pinul pe hartă." });
    }

    const beers = Array.isArray(data.beers) ? data.beers : [];
    const beerStr = beers.map(function (b) {
      const bn = clean(b && b.name);
      const bp = num(b && b.price);
      const bv = clean(b && b.volume);
      const bt = clean(b && b.type);
      if (!bn || bp === "") return null;
      const label = bt ? (bn + " (" + bt + ")") : bn;
      return label + ":" + bp + ":" + bv;
    }).filter(function (x) { return x; }).join(" | ");

    const row = [
      city, name, address, lat, lng, openH, closeH,
      "", "", "", "",   // happy hour left blank — editable later directly in the sheet
      beerStr,
      "",               // tags left blank — editable later directly in the sheet
    ];
    sheet.appendRow(row);

    return jsonOut({ ok: true });
  } catch (err) {
    return jsonOut({ ok: false, error: String(err) });
  }
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
