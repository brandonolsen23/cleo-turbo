/**
 * Cleo Bridge - Content Script for Cleo pages (localhost:5174)
 *
 * This tiny script listens for window.postMessage from the Cleo frontend.
 * When LinkedInButton sends a CLEO_SET_CONTACT message, this script
 * writes the contact context to chrome.storage.session so the LinkedIn
 * content script can pick it up.
 *
 * This is the bridge between the Cleo web app and the Chrome extension.
 */

(function () {
  "use strict";

  window.addEventListener("message", (event) => {
    // Only accept messages from the same page
    if (event.source !== window) return;

    if (event.data?.type === "CLEO_SET_CONTACT") {
      const { contactId, contactName } = event.data;
      if (contactId) {
        chrome.storage.session.set({
          cleoContactId: contactId,
          cleoContactName: contactName || null,
        });
        console.log(
          `[Cleo Bridge] Stored contact context: ${contactId} (${contactName})`
        );
      }
    }
  });

  console.log("[Cleo Bridge] Listening for contact context messages");
})();
