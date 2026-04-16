import { useState, useRef, useEffect } from "react";
import { Text, Button } from "@radix-ui/themes";
import { LinkedinLogo, PencilSimple, Check, X } from "@phosphor-icons/react";
import { mutateApi } from "../../api/client";

const LINKEDIN_URL_REGEX = /^https:\/\/(www\.)?linkedin\.com\/in\/[\w-]+\/?$/;

function buildSearchUrl(name: string): string {
  const keywords = name.trim().split(/\s+/).join("+");
  return `https://www.linkedin.com/search/results/people/?keywords=${keywords}`;
}

export default function LinkedInButton({
  contactId,
  contactName,
  linkedinUrl,
  headline,
  onSaved,
  size = "sm",
}: {
  contactId: string;
  contactName: string;
  linkedinUrl?: string | null;
  headline?: string | null;
  onSaved?: (url: string) => void;
  size?: "sm" | "md";
}) {
  const [showPopover, setShowPopover] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedUrl, setSavedUrl] = useState(linkedinUrl || null);
  const [editing, setEditing] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync with prop changes
  useEffect(() => { setSavedUrl(linkedinUrl || null); }, [linkedinUrl]);

  // Close popover on outside click
  useEffect(() => {
    if (!showPopover) return;
    const handle = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setShowPopover(false);
        setEditing(false);
      }
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [showPopover]);

  // Focus input when popover opens
  useEffect(() => {
    if (showPopover && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showPopover]);

  const handleSave = async () => {
    const url = urlInput.trim();
    if (!LINKEDIN_URL_REGEX.test(url)) {
      setError("Enter a valid LinkedIn profile URL");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await mutateApi(`/contacts/${contactId}`, "PATCH", { linkedin_url: url });
      setSavedUrl(url);
      setShowPopover(false);
      setEditing(false);
      setUrlInput("");
      onSaved?.(url);
    } catch {
      setError("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const iconSize = size === "md" ? 18 : 14;
  const hasUrl = !!savedUrl;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();

    // Always tell the Cleo Bridge which contact we're looking up,
    // so the LinkedIn content script can link the save back to this contact.
    window.postMessage(
      { type: "CLEO_SET_CONTACT", contactId, contactName },
      window.location.origin
    );

    if (hasUrl && !editing) {
      // Small delay to let the bridge script write to storage before the tab opens
      setTimeout(() => {
        window.open(savedUrl!, "_blank");
      }, 100);
    } else {
      setTimeout(() => {
        window.open(buildSearchUrl(contactName), "_blank");
      }, 100);
      // Show popover for pasting URL after search
      setShowPopover(true);
    }
  };

  return (
    <span className="relative inline-flex items-center">
      {/* Main LinkedIn icon */}
      <button
        className="inline-flex items-center gap-0.5 rounded p-0.5 hover:bg-[var(--gray-3)] transition-colors"
        onClick={handleClick}
        title={hasUrl ? (headline || "View on LinkedIn") : "Search LinkedIn"}
      >
        <LinkedinLogo
          size={iconSize}
          weight={hasUrl ? "fill" : "regular"}
          style={{ color: hasUrl ? "var(--jade-9)" : "var(--gray-8)" }}
        />
      </button>

      {/* Edit button (only when URL saved) */}
      {hasUrl && (
        <button
          className="inline-flex items-center p-0.5 rounded hover:bg-[var(--gray-3)] transition-colors opacity-0 group-hover:opacity-100"
          style={{ color: "var(--gray-8)" }}
          onClick={(e) => {
            e.stopPropagation();
            setUrlInput(savedUrl || "");
            setEditing(true);
            setShowPopover(true);
          }}
          title="Edit LinkedIn URL"
        >
          <PencilSimple size={12} />
        </button>
      )}

      {/* Save URL Popover */}
      {showPopover && (
        <div
          ref={popoverRef}
          className="absolute left-0 top-full mt-1 z-50 rounded-lg border border-[var(--gray-6)] bg-white shadow-lg p-3"
          style={{ width: 320 }}
          onClick={(e) => e.stopPropagation()}
        >
          <Text size="2" weight="medium" className="block mb-2">
            {editing ? "Edit LinkedIn URL" : "Save LinkedIn Profile"}
          </Text>
          <input
            ref={inputRef}
            type="url"
            value={urlInput}
            onChange={(e) => { setUrlInput(e.target.value); setError(null); }}
            placeholder="https://linkedin.com/in/..."
            className={`w-full px-2.5 py-1.5 text-[13px] rounded border ${
              error ? "border-[var(--red-7)]" : "border-[var(--gray-6)]"
            } focus:outline-none focus:ring-1 focus:ring-[var(--jade-7)]`}
            onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") setShowPopover(false); }}
          />
          {error && (
            <Text size="1" className="block mt-1" style={{ color: "var(--red-11)" }}>{error}</Text>
          )}
          <div className="flex items-center justify-end gap-2 mt-2.5">
            <button
              className="text-[12px] font-medium hover:underline"
              style={{ color: "var(--gray-9)" }}
              onClick={() => { setShowPopover(false); setEditing(false); setError(null); }}
            >
              Cancel
            </button>
            <Button
              size="1"
              color="jade"
              disabled={saving || !urlInput.trim()}
              onClick={handleSave}
            >
              {saving ? "Saving..." : "Save"}
              {!saving && <Check size={12} />}
            </Button>
          </div>
        </div>
      )}
    </span>
  );
}
