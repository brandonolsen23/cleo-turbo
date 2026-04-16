import { useState, useEffect } from "react";
import { Text } from "@radix-ui/themes";
import { X } from "@phosphor-icons/react";
import { useSourceViewer } from "./SourceViewerContext";

export default function SourceViewerDrawer() {
  const { isOpen, sourceId, closeSource } = useSourceViewer();
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sourceId || !isOpen) return;
    setHtml(null);
    setError(null);

    const token = localStorage.getItem("cleo_token");
    fetch(`/api/transactions/${sourceId}/html`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.text();
      })
      .then(setHtml)
      .catch((err) => setError(err.message));
  }, [sourceId, isOpen]);

  return (
    <>
      {/* Backdrop */}
      <div
        className={`source-drawer-backdrop ${isOpen ? "source-drawer-backdrop--open" : ""}`}
        onClick={closeSource}
      />

      {/* Drawer */}
      <div className={`source-drawer ${isOpen ? "source-drawer--open" : ""}`}>
        {sourceId && (
          <>
            {/* Header */}
            <div
              className="flex items-center justify-between px-5 py-3 border-b"
              style={{ borderColor: "var(--gray-6)" }}
            >
              <div className="flex items-center gap-2">
                <Text size="2" weight="medium">Source HTML</Text>
                <Text size="1" style={{ color: "var(--gray-9)" }}>{sourceId}</Text>
              </div>
              <button
                onClick={closeSource}
                className="p-1 rounded hover:bg-[var(--gray-3)] transition-colors cursor-pointer"
                style={{ color: "var(--gray-9)", border: "none", background: "none" }}
              >
                <X size={16} />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-hidden">
              {error ? (
                <div className="p-5">
                  <Text size="2" style={{ color: "var(--red-9)" }}>Failed to load source: {error}</Text>
                </div>
              ) : !html ? (
                <div className="p-5">
                  <Text size="2" style={{ color: "var(--gray-9)" }}>Loading...</Text>
                </div>
              ) : (
                <iframe
                  key={sourceId}
                  srcDoc={html}
                  title={`Source HTML for ${sourceId}`}
                  className="w-full h-full border-0"
                  sandbox="allow-same-origin"
                />
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
