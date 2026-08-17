/**
 * Bier in HD — Apps Script backend for the Bars sheet.
 *
 * What this does:
 *  - doPost(e): receives the JSON a visitor submits via the "+ Hinzufügen"
 *    form on bier-in-hd.html and appends one row to the target tab, in
 *    the same column layout the frontend's parseSheetRow() expects:
 *      A Name | B Stadtteil/Adresse | C Lat | D Lng | E Öffnet (Std)
 *      F Schließt (Std) | G Biere | H Tags
 *  - doGet(e): trivial health check, so you can confirm the deployment is
 *    live by opening the /exec URL in a browser.
 *
 * This targets the spreadsheet and tab by ID (matching SHEET_ID/SHEET_GID
 * in bier-in-hd.html), not by name — so it works whether this script is
 * bound to that sheet or deployed standalone, and survives the tab being
 * renamed.
 *
 * Setup:
 *  1. Open the Google Sheet at:
 *     https://docs.google.com/spreadsheets/d/1_eEvvCN4kQlhO298_McnxXi1IpFhj4gb42ZAXlCGKRc/edit
 *  2. Extensions > Apps Script, delete the placeholder Code.gs content,
 *     paste this file in, and save.
 *  3. Deploy > New deployment > type "Web app".
 *       - Execute as: Me
 *       - Who has access: Anyone
 *  4. Copy the resulting /exec URL and paste it into ADD_BAR_URL in
 *     bier-in-hd.html.
 *  5. Share the sheet itself as "Anyone with the link — Viewer" so the
 *     page can also *read* it (separate from this script, which only
 *     handles the write side).
 */

var SHEET_ID = "1_eEvvCN4kQlhO298_McnxXi1IpFhj4gb42ZAXlCGKRc";
var SHEET_GID = 1658058362;
var SHEET_TAB_NAME_FALLBACK = "Bars"; // used only if the gid above can't be found

function getTargetSheet() {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  return ss.getSheetById(SHEET_GID) || ss.getSheetByName(SHEET_TAB_NAME_FALLBACK);
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var data = JSON.parse(e.postData.contents);
    var sheet = getTargetSheet();
    if (!sheet) throw new Error("Ziel-Tab nicht gefunden (gid " + SHEET_GID + ").");

    var name = (data.name || "").toString().trim();
    var neighborhood = (data.neighborhood || "").toString().trim();
    var lat = Number(data.lat);
    var lng = Number(data.lng);
    var openHour = Number(data.openHour);
    var closeHour = Number(data.closeHour);
    var beers = Array.isArray(data.beers) ? data.beers : [];

    if (!name || !isFinite(lat) || !isFinite(lng) || !isFinite(openHour) || !isFinite(closeHour) || !beers.length) {
      return jsonOut({ status: "error", message: "Fehlende oder ungültige Felder." });
    }

    var beersStr = beers
      .map(function (b) {
        var beerName = (b.name || "Bier").toString().trim();
        if (b.type) beerName += " (" + b.type + ")";
        var price = Number(b.price) || 0;
        var volume = (b.volume || "").toString().trim();
        return beerName + ":" + price + ":" + volume;
      })
      .join(" | ");

    sheet.appendRow([name, neighborhood, lat, lng, openHour, closeHour, beersStr, ""]);

    return jsonOut({ status: "ok" });
  } catch (err) {
    return jsonOut({ status: "error", message: err.message });
  } finally {
    lock.releaseLock();
  }
}

function doGet(e) {
  return jsonOut({ status: "ok", message: "Bier in HD Apps Script läuft." });
}

function jsonOut(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
