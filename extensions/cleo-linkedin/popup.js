/**
 * Cleo Turbo LinkedIn Capture - Popup Script
 * Settings configuration and connection testing.
 */

const backendUrlInput = document.getElementById("backendUrl");
const tokenInput = document.getElementById("token");
const saveBtn = document.getElementById("saveBtn");
const testBtn = document.getElementById("testBtn");
const statusEl = document.getElementById("status");
const contextBox = document.getElementById("contextBox");
const contextValue = document.getElementById("contextValue");

// Load saved settings
chrome.storage.local.get(["cleoBackendUrl", "cleoToken"], (result) => {
  backendUrlInput.value = result.cleoBackendUrl || "http://localhost:8099";
  tokenInput.value = result.cleoToken || "";
});

// Load contact context
chrome.storage.session.get(["cleoContactId", "cleoContactName"], (result) => {
  if (result.cleoContactId) {
    contextBox.style.display = "block";
    contextValue.textContent = `${result.cleoContactName || "Unknown"} (${result.cleoContactId})`;
  }
});

// Save settings
saveBtn.addEventListener("click", () => {
  const backendUrl = backendUrlInput.value.trim().replace(/\/$/, "");
  const token = tokenInput.value.trim();

  chrome.storage.local.set({ cleoBackendUrl: backendUrl, cleoToken: token }, () => {
    showStatus("Settings saved", "success");
  });
});

// Test connection
testBtn.addEventListener("click", async () => {
  const backendUrl = backendUrlInput.value.trim().replace(/\/$/, "");
  const token = tokenInput.value.trim();

  if (!token) {
    showStatus("Enter an auth token first", "error");
    return;
  }

  showStatus("Testing...", "success");

  chrome.runtime.sendMessage(
    { type: "TEST_CONNECTION", backendUrl, token },
    (response) => {
      if (response?.ok) {
        showStatus("Connected to Cleo", "success");
      } else {
        showStatus(response?.error || "Connection failed", "error");
      }
    }
  );
});

function showStatus(message, type) {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
}
