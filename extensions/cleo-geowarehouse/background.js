// Cleo Turbo — GeoWarehouse capture (background service worker).
//
// Receives a base64 HTML snapshot from the content script and saves it into
// Downloads/GeoWarehouse/gw-ingest-data/ as geowarehouse-<ISO>.html — exactly
// where the Cleo GW ingester looks. Silent (no Save-As) as long as Chrome's
// "Ask where to save each file before downloading" setting is OFF.
//
// The toolbar icon doubles as a status light: GREEN badge = armed & watching,
// YELLOW flash = a report was just captured, RED = a save failed.

const SUBDIR = "GeoWarehouse/gw-ingest-data";
const GREEN = "#1a7f5a";
const YELLOW = "#e0a800";
const RED = "#b42318";

function setIdleBadge() {
  chrome.action.setBadgeBackgroundColor({ color: GREEN });
  chrome.storage.local.get({ count: 0 }, (s) => {
    chrome.action.setBadgeText({ text: s.count ? String(s.count) : "ON" });
  });
}

function flash(color, text, thenIdle = true) {
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
  if (thenIdle) setTimeout(setIdleBadge, 1800);
}

chrome.runtime.onStartup.addListener(setIdleBadge);
chrome.runtime.onInstalled.addListener(setIdleBadge);
setIdleBadge();

function filename() {
  // toISOString() with ':' and '.' swapped to '-', matching existing captures.
  return "geowarehouse-" + new Date().toISOString().replace(/[:.]/g, "-") + ".html";
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.type !== "cleo-gw-capture") return;

  const name = `${SUBDIR}/${filename()}`;
  const dataUrl = "data:text/html;charset=utf-8;base64," + msg.b64;

  chrome.downloads.download(
    { url: dataUrl, filename: name, conflictAction: "uniquify", saveAs: false },
    (downloadId) => {
      const ok = !chrome.runtime.lastError && downloadId != null;
      const err = chrome.runtime.lastError ? String(chrome.runtime.lastError.message) : "";
      chrome.storage.local.get({ count: 0 }, (s) => {
        chrome.storage.local.set({
          count: s.count + (ok ? 1 : 0),
          lastFile: name,
          lastPin: msg.pin || "",
          lastUrl: msg.url || "",
          lastAt: Date.now(),
          lastOk: ok,
          lastErr: err,
        });
        if (ok) flash(YELLOW, "SAVE");
        else flash(RED, "ERR", false);
      });
    }
  );
  sendResponse({ received: true });
  return true; // async response
});
