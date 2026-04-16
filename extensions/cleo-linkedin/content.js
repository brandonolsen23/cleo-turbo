/**
 * Cleo Turbo LinkedIn Capture - Content Script
 *
 * Injected on linkedin.com/* pages.
 * On profile pages (/in/*), injects a floating "Save to Cleo" button.
 * Extracts work history from the DOM and sends it to the Cleo backend.
 *
 * When Datanyze is detected (div#Datanyze in the page), shows a compact
 * capture panel with 2 email slots + 3 phone slots. Datanyze renders in
 * a cross-origin chrome-extension:// iframe, so we use clipboard capture.
 *
 * Contact context (which Cleo contact to attach data to) is set by
 * cleo_bridge.js on the Cleo page via chrome.storage.session, BEFORE
 * the LinkedIn tab even opens.
 */

(function () {
  "use strict";

  // ── State ──────────────────────────────────────────────────
  let contactId = null;
  let contactName = null;
  let buttonEl = null;
  let panelEl = null;
  let datanyzeDetected = false;

  // Captured contact details — fixed slots
  const MAX_EMAILS = 2;
  const MAX_PHONES = 3;
  let capturedEmails = []; // { value, type, source }
  let capturedPhones = []; // { value, type, source }

  // ── Datanyze Detection ─────────────────────────────────────

  let datanyzeObserver = null;

  function startDatanyzeWatch() {
    if (!window.__cleoDatanyze) {
      console.warn("[Cleo] Datanyze helper not loaded — skipping watch");
      return;
    }

    datanyzeObserver = window.__cleoDatanyze.watchForDatanyze(() => {
      datanyzeDetected = true;
      console.log("[Cleo] Datanyze detected on page");
      showDatanyzePanel();
    });
  }

  // ── Datanyze Capture Panel ─────────────────────────────────

  function showDatanyzePanel() {
    if (panelEl) return;
    if (!buttonEl) return;

    panelEl = document.createElement("div");
    panelEl.id = "cleo-datanyze-panel";
    renderPanel();

    // Insert panel above the button
    const wrapper = buttonEl.querySelector(".cleo-btn-wrapper");
    wrapper.insertBefore(panelEl, wrapper.firstChild);
  }

  function renderPanel() {
    if (!panelEl) return;

    // Build email slots
    let emailSlots = "";
    for (let i = 0; i < MAX_EMAILS; i++) {
      const item = capturedEmails[i];
      if (item) {
        emailSlots += `
          <div class="cleo-dn-item">
            <span class="cleo-dn-item-value">${item.value}</span>
            <span class="cleo-dn-item-type">${item.type}</span>
            <button class="cleo-dn-item-remove" data-type="email" data-index="${i}">×</button>
          </div>`;
      } else {
        emailSlots += `
          <button class="cleo-dn-paste-btn" data-action="paste-email" data-index="${i}">
            <span class="cleo-dn-paste-icon">📋</span> Paste Email ${i + 1}
          </button>`;
      }
    }

    // Build phone slots
    let phoneSlots = "";
    for (let i = 0; i < MAX_PHONES; i++) {
      const item = capturedPhones[i];
      if (item) {
        phoneSlots += `
          <div class="cleo-dn-item">
            <span class="cleo-dn-item-value">${item.value}</span>
            <span class="cleo-dn-item-type">${item.type}</span>
            <button class="cleo-dn-item-remove" data-type="phone" data-index="${i}">×</button>
          </div>`;
      } else {
        phoneSlots += `
          <button class="cleo-dn-paste-btn" data-action="paste-phone" data-index="${i}">
            <span class="cleo-dn-paste-icon">📋</span> Paste Phone ${i + 1}
          </button>`;
      }
    }

    panelEl.innerHTML = `
      <div class="cleo-dn-header">
        <span class="cleo-dn-icon">⚡</span>
        <span>Datanyze detected</span>
        <button class="cleo-dn-close" title="Dismiss">×</button>
      </div>
      <div class="cleo-dn-hint">Copy from Datanyze, then paste here</div>
      <div class="cleo-dn-section">
        <div class="cleo-dn-section-label">Emails</div>
        <div class="cleo-dn-slots">${emailSlots}</div>
      </div>
      <div class="cleo-dn-section">
        <div class="cleo-dn-section-label">Phones</div>
        <div class="cleo-dn-slots">${phoneSlots}</div>
      </div>
    `;

    // Wire up events
    panelEl.querySelector(".cleo-dn-close").addEventListener("click", () => {
      panelEl.remove();
      panelEl = null;
    });

    panelEl.querySelectorAll("[data-action='paste-email']").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.currentTarget.dataset.index, 10);
        pasteItem("email", idx, e.currentTarget);
      });
    });

    panelEl.querySelectorAll("[data-action='paste-phone']").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.currentTarget.dataset.index, 10);
        pasteItem("phone", idx, e.currentTarget);
      });
    });

    panelEl.querySelectorAll(".cleo-dn-item-remove").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const itemType = e.target.dataset.type;
        const idx = parseInt(e.target.dataset.index, 10);
        if (itemType === "email") capturedEmails.splice(idx, 1);
        else capturedPhones.splice(idx, 1);
        renderPanel();
        updateSaveButtonLabel();
      });
    });
  }

  async function pasteItem(type, slotIndex, btnEl) {
    try {
      const text = await navigator.clipboard.readText();
      const cleaned = text.trim();
      if (!cleaned) {
        flashButton(btnEl, "Nothing on clipboard", false);
        return;
      }

      if (type === "email") {
        const emailRe = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/;
        const match = cleaned.match(emailRe);
        if (!match) {
          flashButton(btnEl, "Not an email", false);
          return;
        }
        const email = match[0].toLowerCase();
        if (capturedEmails.some((e) => e.value === email)) {
          flashButton(btnEl, "Already added", false);
          return;
        }
        let emailType = "work";
        if (email.match(/@(gmail|yahoo|hotmail|outlook|aol|icloud|me|proton)\./i)) {
          emailType = "personal";
        }
        // Fill the slot
        capturedEmails[slotIndex] = { value: email, type: emailType, source: "datanyze_clipboard" };
      } else {
        const digits = cleaned.replace(/\D/g, "");
        if (digits.length < 7) {
          flashButton(btnEl, "Not a phone number", false);
          return;
        }
        const displayValue = cleaned.replace(/\s*\(.*?\)\s*$/, "").trim();
        if (capturedPhones.some((p) => p.value === displayValue)) {
          flashButton(btnEl, "Already added", false);
          return;
        }
        // Detect type from clipboard text
        let phoneType = "unknown";
        const lower = cleaned.toLowerCase();
        if (lower.includes("mobile") || lower.includes("cell")) phoneType = "mobile";
        else if (lower.includes("direct")) phoneType = "direct";
        else if (lower.includes("hq") || lower.includes("headquarters") || lower.includes("office")) phoneType = "hq";

        capturedPhones[slotIndex] = { value: displayValue, type: phoneType, source: "datanyze_clipboard" };
      }

      // Update state in helper
      if (window.__cleoDatanyze) {
        window.__cleoDatanyze.setCapturedData({
          emails: capturedEmails.filter(Boolean),
          phones: capturedPhones.filter(Boolean),
        });
      }

      renderPanel();
      updateSaveButtonLabel();
    } catch (err) {
      console.error("[Cleo] Clipboard read failed:", err);
      flashButton(btnEl, "Clipboard access denied", false);
    }
  }

  function flashButton(btn, message, success) {
    if (!btn) return;
    const originalHTML = btn.innerHTML;
    btn.innerHTML = `<span style="color: ${success ? "#16a34a" : "#dc2626"}">${message}</span>`;
    btn.disabled = true;
    setTimeout(() => {
      btn.innerHTML = originalHTML;
      btn.disabled = false;
    }, 1500);
  }

  function updateSaveButtonLabel() {
    if (!buttonEl) return;
    const label = buttonEl.querySelector(".cleo-label");
    if (!label) return;

    const base = contactName
      ? `Save to Cleo — ${contactName}`
      : contactId
        ? `Save to Cleo — ${contactId}`
        : "Save to Cleo";

    const emails = capturedEmails.filter(Boolean);
    const phones = capturedPhones.filter(Boolean);
    const parts = [];
    if (emails.length > 0) parts.push(`${emails.length} email${emails.length > 1 ? "s" : ""}`);
    if (phones.length > 0) parts.push(`${phones.length} phone${phones.length > 1 ? "s" : ""}`);

    if (parts.length > 0) {
      label.textContent = `${base} (+ ${parts.join(", ")})`;
    } else {
      label.textContent = base;
    }
  }

  // ── Contact Context ────────────────────────────────────────

  chrome.storage.session.onChanged.addListener((changes) => {
    if (changes.cleoContactId?.newValue) {
      contactId = changes.cleoContactId.newValue;
      contactName = changes.cleoContactName?.newValue || null;
      console.log(`[Cleo] Contact context updated: ${contactId} (${contactName})`);
      updateButtonLabel();
    }
  });

  async function loadContactContext() {
    try {
      const result = await chrome.storage.session.get([
        "cleoContactId",
        "cleoContactName",
      ]);
      if (result.cleoContactId) {
        contactId = result.cleoContactId;
        contactName = result.cleoContactName || null;
        console.log(
          `[Cleo] Loaded contact context: ${contactId} (${contactName})`
        );
        return true;
      }
    } catch (e) {
      // Ignore
    }
    console.log("[Cleo] No contact context found in session storage");
    return false;
  }

  function isProfilePage() {
    return window.location.pathname.startsWith("/in/");
  }

  // ── Image Extraction ────────────────────────────────────────

  function extractProfilePhoto() {
    const selectors = [
      'img.pv-top-card-profile-picture__image--show',
      'img.pv-top-card-profile-picture__image',
      'img[class*="pv-top-card-profile-picture"]',
      '.pv-top-card__photo-wrapper img',
      'img.profile-photo-edit__preview',
      '.pv-top-card img[src*="profile"]',
    ];

    for (const sel of selectors) {
      const img = document.querySelector(sel);
      if (img && img.src && !img.src.includes("ghost") && !img.src.includes("default")) {
        return img.src;
      }
    }

    const nameEl = document.querySelector("h1");
    if (nameEl) {
      const section = nameEl.closest("section") || nameEl.closest('[class*="top-card"]') || nameEl.parentElement?.parentElement?.parentElement;
      if (section) {
        const imgs = section.querySelectorAll("img");
        for (const img of imgs) {
          const src = img.src || "";
          if (
            src &&
            !src.includes("ghost") &&
            !src.includes("default") &&
            !src.includes("/company/") &&
            !src.includes("/school/") &&
            img.width >= 50
          ) {
            return src;
          }
        }
      }
    }

    return null;
  }

  function extractCompanyLogo(el) {
    const imgs = el.querySelectorAll("img");
    for (const img of imgs) {
      const src = img.src || "";
      if (
        src &&
        !src.includes("ghost") &&
        !src.includes("default") &&
        (src.includes("/company/") || src.includes("company-logo") || img.width <= 72)
      ) {
        return src;
      }
    }
    return null;
  }

  // ── DOM Extraction ─────────────────────────────────────────

  function findSectionByHeading(headingText) {
    const sections = document.querySelectorAll("section");
    for (const section of sections) {
      const headings = section.querySelectorAll(
        "h2, [class*='pvs-header'] span, div[class*='display-flex'] span"
      );
      for (const h of headings) {
        const text = h.textContent?.trim().toLowerCase();
        if (text === headingText.toLowerCase()) {
          return section;
        }
      }
    }
    const byId = document.querySelector(
      '#experience, [aria-label="Experience"]'
    );
    if (byId) return byId.closest("section") || byId;
    return null;
  }

  function parseDateToYYYYMM(dateStr) {
    if (!dateStr) return null;
    dateStr = dateStr.trim();
    if (dateStr.toLowerCase() === "present") return null;

    const months = {
      jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
      jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12",
    };

    const match = dateStr.match(/^(\w+)\s+(\d{4})$/);
    if (match) {
      const monthKey = match[1].substring(0, 3).toLowerCase();
      const month = months[monthKey];
      return month ? `${match[2]}-${month}` : match[2];
    }

    const yearMatch = dateStr.match(/^(\d{4})$/);
    if (yearMatch) return yearMatch[1];

    return null;
  }

  function extractDateRange(text) {
    if (!text) return null;
    const cleaned = text.split("·")[0].trim();
    const parts = cleaned.split(/\s*[-–—]\s*/);
    if (parts.length >= 2) {
      return { start: parts[0].trim(), end: parts[1].trim() };
    }
    return null;
  }

  function looksLikeDateRange(text) {
    return /\d{4}/.test(text) && /[-–—]/.test(text);
  }

  function looksLikeDuration(text) {
    return /^\d+\s*(yr|mo|year|month)/i.test(text.trim());
  }

  function looksLikeLocation(text) {
    return text.includes(",") && !text.includes("·") && !/\d{4}/.test(text) && text.length < 80;
  }

  function isCompanyDescriptionCard(el) {
    const text = el.textContent?.trim() || "";
    if (text.length > 200 && !looksLikeDateRange(text)) return true;
    if (el.querySelector("img, video, [class*='media']") && !looksLikeDateRange(text)) return true;
    return false;
  }

  function getDirectSpans(el) {
    const spans = el.querySelectorAll("span[aria-hidden='true']");
    const nestedUl = el.querySelector("ul");
    const results = [];
    for (const span of spans) {
      if (nestedUl && nestedUl.contains(span)) continue;
      const text = span.textContent?.trim();
      if (text) results.push(text);
    }
    return results;
  }

  function extractExperience() {
    const profileUrl = window.location.href.split("?")[0].replace(/\/$/, "");

    const nameEl = document.querySelector("h1");
    const headlineEl = document.querySelector(
      ".text-body-medium, [data-generated-suggestion-target]"
    );
    const profileName = nameEl?.textContent?.trim() || null;
    const headline = headlineEl?.textContent?.trim() || null;

    const experienceSection = findSectionByHeading("Experience");
    if (!experienceSection) {
      return {
        error:
          "Could not find Experience section. Try scrolling down to load it, then try again.",
        linkedin_url: profileUrl,
        headline,
        positions: [],
      };
    }

    const positions = [];
    const listItems = experienceSection.querySelectorAll(
      ":scope > div > div > ul > li, :scope > div > ul > li"
    );

    for (const li of listItems) {
      const subList = li.querySelector("ul");

      if (subList) {
        const parentTexts = getDirectSpans(li);
        const companyLink = li.querySelector('a[href*="/company/"]');
        let company = companyLink?.textContent?.trim() || null;

        if (!company && parentTexts.length > 0) {
          for (const t of parentTexts) {
            if (!looksLikeDateRange(t) && !looksLikeDuration(t) && !looksLikeLocation(t)) {
              company = t;
              break;
            }
          }
        }

        const parentLogo = extractCompanyLogo(li);
        const subItems = subList.querySelectorAll(":scope > li");
        let foundRealSubPosition = false;

        for (const sub of subItems) {
          if (isCompanyDescriptionCard(sub)) continue;
          const pos = extractSinglePosition(sub, company);
          if (pos && pos.title) {
            if (!pos.company_logo_url && parentLogo) {
              pos.company_logo_url = parentLogo;
            }
            positions.push(pos);
            foundRealSubPosition = true;
          }
        }

        if (!foundRealSubPosition) {
          const pos = extractFromParentTexts(parentTexts, company);
          if (pos) positions.push(pos);
        }
      } else {
        const pos = extractSinglePosition(li, null);
        if (pos) positions.push(pos);
      }
    }

    const cleaned = positions.filter((p) => {
      if (!p.title && !p.start_date && !p.end_date && !p.is_current) return false;
      return true;
    });

    const profilePhoto = extractProfilePhoto();

    return {
      linkedin_url: profileUrl,
      headline,
      profile_name: profileName,
      profile_photo_url: profilePhoto,
      positions: cleaned,
    };
  }

  function extractFromParentTexts(texts, company) {
    let title = null;
    let dateStr = null;
    let location = null;

    for (const text of texts) {
      if (!dateStr && looksLikeDateRange(text)) { dateStr = text; continue; }
      if (!location && looksLikeLocation(text)) { location = text; continue; }
      if (looksLikeDuration(text)) continue;
      if (text === company) continue;
      if (!title) { title = text; continue; }
    }

    if (!company && !title) return null;

    const dateRange = extractDateRange(dateStr);
    const startDate = dateRange ? parseDateToYYYYMM(dateRange.start) : null;
    const endDateRaw = dateRange ? dateRange.end : null;
    const isCurrent = endDateRaw?.toLowerCase() === "present";
    const endDate = isCurrent ? null : parseDateToYYYYMM(endDateRaw);

    return {
      company: company || "Unknown Company",
      title: title || null,
      start_date: startDate,
      end_date: endDate,
      is_current: isCurrent,
      location: location || null,
      company_logo_url: null,
    };
  }

  function extractSinglePosition(el, parentCompany) {
    const spans = el.querySelectorAll("span[aria-hidden='true']");
    const nestedUl = el.querySelector("ul");
    const texts = [];
    for (const s of spans) {
      if (nestedUl && nestedUl.contains(s)) continue;
      const t = s.textContent?.trim();
      if (t) texts.push(t);
    }

    if (texts.length === 0) return null;

    let title = null;
    let company = parentCompany;
    let dateStr = null;
    let location = null;

    for (const text of texts) {
      if (!dateStr && looksLikeDateRange(text)) { dateStr = text; continue; }
      if (!location && looksLikeLocation(text)) { location = text; continue; }
    }

    for (const text of texts) {
      if (text === dateStr || text === location) continue;
      if (looksLikeDuration(text)) continue;
      if (!title) { title = text; continue; }
      if (!company) {
        company = text.replace(/\s*·.*$/, "").trim();
        continue;
      }
    }

    if (!company) {
      const companyLink = el.querySelector('a[href*="/company/"]');
      if (companyLink) {
        company = companyLink.textContent?.trim();
      }
    }

    if (!company && !title) return null;

    const dateRange = extractDateRange(dateStr);
    const startDate = dateRange ? parseDateToYYYYMM(dateRange.start) : null;
    const endDateRaw = dateRange ? dateRange.end : null;
    const isCurrent = endDateRaw?.toLowerCase() === "present";
    const endDate = isCurrent ? null : parseDateToYYYYMM(endDateRaw);

    return {
      company: company || "Unknown Company",
      title: title || null,
      start_date: startDate,
      end_date: endDate,
      is_current: isCurrent,
      location: location || null,
      company_logo_url: extractCompanyLogo(el),
    };
  }

  // ── API Communication ──────────────────────────────────────

  async function getConfig() {
    const result = await chrome.storage.local.get(["cleoBackendUrl", "cleoToken"]);
    return {
      backendUrl: result.cleoBackendUrl || "http://localhost:8099",
      token: result.cleoToken || null,
    };
  }

  async function sendToCleo(cid, data) {
    const { backendUrl, token } = await getConfig();
    if (!token) {
      throw new Error("No Cleo auth token configured. Open the extension popup to set it up.");
    }
    if (!cid) {
      throw new Error("No contact ID linked.");
    }

    const response = await fetch(
      `${backendUrl}/api/contacts/${cid}/linkedin-profile`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      }
    );

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Cleo API error (${response.status}): ${text}`);
    }
    return response.json();
  }

  // ── Floating Button ────────────────────────────────────────

  function injectButton() {
    if (buttonEl) return;

    buttonEl = document.createElement("div");
    buttonEl.id = "cleo-linkedin-capture";
    buttonEl.innerHTML = `
      <div class="cleo-btn-wrapper">
        <button class="cleo-save-btn" title="Save to Cleo">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                  stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <div class="cleo-label"></div>
        <div class="cleo-status" style="display:none"></div>
      </div>
    `;

    document.body.appendChild(buttonEl);

    const label = buttonEl.querySelector(".cleo-label");
    if (contactName) {
      label.textContent = `Save to Cleo — ${contactName}`;
    } else if (contactId) {
      label.textContent = `Save to Cleo — ${contactId}`;
    } else {
      label.textContent = "Save to Cleo";
    }
    label.style.display = "block";

    const btn = buttonEl.querySelector(".cleo-save-btn");
    btn.addEventListener("click", handleSaveClick);
  }

  async function handleSaveClick() {
    const btn = buttonEl.querySelector(".cleo-save-btn");
    const status = buttonEl.querySelector(".cleo-status");

    btn.classList.add("cleo-loading");
    status.style.display = "none";

    try {
      if (!contactId) {
        await loadContactContext();
      }

      if (!contactId) {
        showStatus(
          "No contact ID linked. Open this profile from Cleo to auto-link.",
          "error"
        );
        btn.classList.remove("cleo-loading");
        return;
      }

      const data = extractExperience();
      if (data.error) {
        showStatus(data.error, "error");
        btn.classList.remove("cleo-loading");
        return;
      }

      console.log("[Cleo] Extracted positions:", JSON.stringify(data.positions, null, 2));

      const payload = {
        linkedin_url: data.linkedin_url,
        headline: data.headline,
        profile_photo_url: data.profile_photo_url || null,
        positions: data.positions,
      };

      // Attach captured contact details (from clipboard pastes)
      const emails = capturedEmails.filter(Boolean);
      const phones = capturedPhones.filter(Boolean);
      if (emails.length > 0 || phones.length > 0) {
        payload.contact_details = { emails, phones };
        console.log("[Cleo] Including contact details:", payload.contact_details);
      }

      const result = await sendToCleo(contactId, payload);

      const parts = [`${result.positions_saved} positions`];
      if (result.contact_details_saved) {
        parts.push("contact details");
      }
      showStatus(`Saved ${parts.join(" + ")} to Cleo`, "success");
      btn.classList.remove("cleo-loading");
      btn.classList.add("cleo-success");

      chrome.storage.session.remove(["cleoContactId", "cleoContactName"]);
    } catch (err) {
      showStatus(err.message, "error");
      btn.classList.remove("cleo-loading");
    }
  }

  function showStatus(message, type) {
    const status = buttonEl.querySelector(".cleo-status");
    status.textContent = message;
    status.className = `cleo-status cleo-status-${type}`;
    status.style.display = "block";

    if (type === "success") {
      setTimeout(() => { status.style.display = "none"; }, 5000);
    }
  }

  // ── Init ───────────────────────────────────────────────────

  async function initUI() {
    if (!isProfilePage()) return;

    await loadContactContext();
    injectButton();
    startDatanyzeWatch();

    updateButtonLabel();
  }

  function updateButtonLabel() {
    if (!buttonEl) return;
    const label = buttonEl.querySelector(".cleo-label");
    if (!label) return;
    if (contactName) {
      label.textContent = `Save to Cleo — ${contactName}`;
    } else if (contactId) {
      label.textContent = `Save to Cleo — ${contactId}`;
    } else {
      label.textContent = "Save to Cleo";
    }
  }

  /**
   * LinkedIn is a SPA — navigating between profiles doesn't trigger
   * a full page load, so our content script only runs once.
   * Watch for URL changes and re-init when the profile changes.
   */
  let lastUrl = location.href;
  function watchForNavigation() {
    const observer = new MutationObserver(() => {
      if (location.href !== lastUrl) {
        lastUrl = location.href;
        // Reset state for the new profile
        capturedEmails = [];
        capturedPhones = [];
        datanyzeDetected = false;
        if (datanyzeObserver) {
          datanyzeObserver.disconnect();
          datanyzeObserver = null;
        }
        if (panelEl) {
          panelEl.remove();
          panelEl = null;
        }
        if (buttonEl) {
          buttonEl.remove();
          buttonEl = null;
        }
        setTimeout(initUI, 1500);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      setTimeout(initUI, 1500);
      watchForNavigation();
    });
  } else {
    setTimeout(initUI, 1500);
    watchForNavigation();
  }
})();
