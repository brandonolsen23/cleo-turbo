/**
 * Shadow DOM Patch — MAIN World Script
 *
 * Forces all shadow roots to be "open" so our content script can
 * traverse into them. This is needed because Datanyze creates a
 * closed shadow root (mode: "closed"), which makes .shadowRoot
 * return null from outside code.
 *
 * This script MUST run in the MAIN world (page context) at
 * document_start — before Datanyze attaches its shadow root.
 *
 * Technique: override Element.prototype.attachShadow to force
 * { mode: "open" } on all calls. This is a standard approach
 * used by accessibility tools and browser extensions.
 */

(function () {
  "use strict";

  const _origAttachShadow = Element.prototype.attachShadow;

  Element.prototype.attachShadow = function (init) {
    // Force open mode so content scripts can access via .shadowRoot
    return _origAttachShadow.call(this, { ...init, mode: "open" });
  };
})();
