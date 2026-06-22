// Popup: show capture + liveness status from chrome.storage.local.
function ago(ts) {
  if (!ts) return "never";
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.round(s / 60) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}

chrome.storage.local.get(
  { count: 0, lastOk: null, lastPin: "", lastAt: 0, lastErr: "", lastAliveAt: 0 },
  (s) => {
    document.getElementById("count").textContent = s.count;

    // Liveness: was the capture script seen on a GW page recently?
    const alive = document.getElementById("alive");
    alive.textContent = ago(s.lastAliveAt);
    alive.className = "v " + (!s.lastAliveAt ? "muted" : (Date.now() - s.lastAliveAt < 86400000 ? "ok" : "warn"));

    const status = document.getElementById("status");
    if (s.lastOk === null) { status.textContent = "no captures yet"; status.className = "v muted"; }
    else if (s.lastOk) { status.textContent = "saved ✓"; status.className = "v ok"; }
    else { status.textContent = "failed"; status.className = "v bad"; }

    document.getElementById("when").textContent = ago(s.lastAt);
    document.getElementById("pin").textContent = s.lastPin || "—";
    if (s.lastErr) document.getElementById("err").textContent = "Error: " + s.lastErr;
  }
);
