// Cleo Turbo — GeoWarehouse capture (content script).
//
// GeoWarehouse is an Angular single-page app, so we can't rely on page loads.
// We watch the DOM; when the property registry panel (#pr-expansion-panel-registry)
// is present and the page has settled, we snapshot the fully-rendered HTML and
// hand it to the background worker to save. De-duped per PIN so clicking around
// the same property doesn't save it repeatedly.

const READY_ID = "pr-expansion-panel-registry"; // present only when the report has rendered
const PIN_ID = "reg-pin";                        // used to de-dupe captures
const SETTLE_MS = 1200;                          // let Angular finish painting

const captured = new Set();
let timer = null;

// Property is selected by the ?pin= query param on /ui/home (SPA navigation).
function urlPin() {
  try { return new URLSearchParams(location.search).get("pin") || ""; }
  catch (e) { return ""; }
}

function currentPin() {
  const el = document.getElementById(PIN_ID);
  return el ? el.textContent.trim() : "";
}

function tryCapture() {
  if (!document.getElementById(READY_ID)) return;
  const key = urlPin() || currentPin() || location.href;
  if (!key || captured.has(key)) return;

  clearTimeout(timer);
  timer = setTimeout(() => {
    if (!document.getElementById(READY_ID)) return; // panel gone again
    const pin = currentPin() || urlPin();
    const k = urlPin() || pin || location.href;
    if (captured.has(k)) return;
    captured.add(k);

    const html = "<!DOCTYPE html>\n" + document.documentElement.outerHTML;
    // Encode here (content script has full window APIs) so the worker just saves.
    const b64 = btoa(unescape(encodeURIComponent(html)));
    chrome.runtime.sendMessage(
      { type: "cleo-gw-capture", b64, pin, url: location.href },
      () => void chrome.runtime.lastError // ignore "no receiver" noise
    );
  }, SETTLE_MS);
}

const observer = new MutationObserver(() => tryCapture());
observer.observe(document.documentElement, { childList: true, subtree: true });
document.addEventListener("DOMContentLoaded", tryCapture);
tryCapture();
