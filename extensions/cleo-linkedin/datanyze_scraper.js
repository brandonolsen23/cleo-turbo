/**
 * Datanyze Capture Helper
 *
 * Datanyze renders inside a chrome-extension:// iframe that our content
 * script cannot access (cross-origin browser security). Instead of DOM
 * scraping, this module:
 *
 * 1. Detects when Datanyze is present on the page (div#Datanyze)
 * 2. Provides a clipboard-based capture UI for emails/phones
 * 3. Manages the captured contact details state
 *
 * Exports (via window.__cleoDatanyze):
 *   - isDatanyzePresent()  → boolean
 *   - getCapturedData()    → { emails: [...], phones: [...] } | null
 *   - setCapturedData(data) → void
 *   - watchForDatanyze(callback) → MutationObserver
 */

(function () {
  "use strict";

  let capturedData = null;

  /**
   * Check if Datanyze's container div is present in the LinkedIn page DOM.
   * The actual content is in a cross-origin iframe we can't access,
   * but the wrapper div tells us Datanyze is active.
   */
  function isDatanyzePresent() {
    return !!document.querySelector("div#Datanyze");
  }

  function getCapturedData() {
    return capturedData;
  }

  function setCapturedData(data) {
    capturedData = data;
  }

  /**
   * Watch for Datanyze's container to appear on the page.
   * Calls back when detected so the UI can update.
   */
  function watchForDatanyze(callback) {
    // Check immediately
    if (isDatanyzePresent()) {
      callback({ datanyzeDetected: true });
    }

    // Watch for DOM changes (Datanyze injects after page load)
    let reported = isDatanyzePresent();
    const observer = new MutationObserver(() => {
      if (!reported && isDatanyzePresent()) {
        reported = true;
        callback({ datanyzeDetected: true });
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });

    return observer;
  }

  // ── Export ─────────────────────────────────────────────────

  window.__cleoDatanyze = {
    isDatanyzePresent,
    getCapturedData,
    setCapturedData,
    watchForDatanyze,
  };

  console.log("[Cleo Datanyze] Capture helper loaded (clipboard mode)");
})();
