/**
 * Cleo Turbo LinkedIn Capture - Background Service Worker
 *
 * Handles messages from popup and content scripts.
 * Stores contact context when LinkedIn is opened from Cleo.
 */

// CRITICAL: Grant content scripts access to chrome.storage.session.
// By default, only the service worker can use session storage.
// Content scripts (cleo_bridge.js, content.js) need this to pass
// the contact ID from the Cleo page to the LinkedIn profile page.
chrome.storage.session.setAccessLevel({
  accessLevel: "TRUSTED_AND_UNTRUSTED_CONTEXTS",
});

// Listen for messages from Cleo frontend (via window.postMessage → content script → here)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "SET_CONTACT_CONTEXT") {
    // Store contact context for the content script to pick up
    chrome.storage.session.set({
      cleoContactId: message.contactId,
      cleoContactName: message.contactName,
    });
    sendResponse({ ok: true });
    return true;
  }

  if (message.type === "TEST_CONNECTION") {
    // Test connectivity to Cleo backend
    testConnection(message.backendUrl, message.token)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true; // Indicates async response
  }

  if (message.type === "SEARCH_CONTACTS") {
    // Search Cleo contacts by name (for manual matching)
    searchContacts(message.backendUrl, message.token, message.query)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});

async function testConnection(backendUrl, token) {
  try {
    const response = await fetch(`${backendUrl}/api/contacts/filters`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) {
      return { ok: true };
    }
    return { ok: false, error: `HTTP ${response.status}` };
  } catch (err) {
    return { ok: false, error: "Cannot reach Cleo backend" };
  }
}

async function searchContacts(backendUrl, token, query) {
  try {
    const response = await fetch(
      `${backendUrl}/api/contacts/search?q=${encodeURIComponent(query)}&limit=10`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}` };
    }
    const data = await response.json();
    return { ok: true, results: data.results };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}
