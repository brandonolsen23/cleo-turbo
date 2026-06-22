// Popup: show capture status from chrome.storage.local.
chrome.storage.local.get(
  { count: 0, lastOk: null, lastPin: "", lastAt: 0, lastErr: "" },
  (s) => {
    document.getElementById("count").textContent = s.count;
    const status = document.getElementById("status");
    if (s.lastOk === null) { status.textContent = "no captures yet"; status.className = "v muted"; }
    else if (s.lastOk) { status.textContent = "saved ✓"; status.className = "v ok"; }
    else { status.textContent = "failed"; status.className = "v bad"; }
    document.getElementById("pin").textContent = s.lastPin || "—";
    document.getElementById("when").textContent = s.lastAt
      ? new Date(s.lastAt).toLocaleString()
      : "—";
    if (s.lastErr) document.getElementById("err").textContent = "Error: " + s.lastErr;
  }
);
