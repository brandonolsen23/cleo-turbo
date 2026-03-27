import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Text, Badge } from "@radix-ui/themes";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { fetchApi } from "../../api/client";

interface SearchResult {
  type: "property" | "contact" | "group";
  id: string;
  title: string;
  subtitle: string | null;
}

export default function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Global Cmd+K listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  // Focus input when opening
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery("");
      setResults([]);
      setSelectedIndex(0);
    }
  }, [open]);

  // Debounced search
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchApi<{ results: SearchResult[] }>("/omnisearch", { q: query, limit: "6" })
        .then((data) => {
          setResults(data.results);
          setSelectedIndex(0);
        });
    }, 200);
  }, [query]);

  const navigateTo = useCallback((r: SearchResult) => {
    setOpen(false);
    switch (r.type) {
      case "property": navigate(`/properties/${r.id}`); break;
      case "contact": navigate(`/contacts/${r.id}`); break;
      case "group": navigate(`/groups/${r.id}`); break;
    }
  }, [navigate]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[selectedIndex]) {
      e.preventDefault();
      navigateTo(results[selectedIndex]);
    }
  };

  const typeColor = (t: string) => {
    switch (t) {
      case "property": return "jade" as const;
      case "contact": return "blue" as const;
      case "group": return "amber" as const;
      default: return "gray" as const;
    }
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0"
        style={{ zIndex: 100, background: "rgba(0,0,0,0.2)" }}
        onClick={() => setOpen(false)}
      />

      {/* Dialog */}
      <div
        className="fixed left-1/2 -translate-x-1/2 rounded-xl border bg-white overflow-hidden"
        style={{
          zIndex: 101,
          top: "20%",
          width: 520,
          borderColor: "var(--gray-6)",
          boxShadow: "var(--elevation-4)",
        }}
      >
        {/* Search input */}
        <div className="flex items-center gap-2 px-4 border-b" style={{ borderColor: "var(--gray-4)" }}>
          <MagnifyingGlass size={18} style={{ color: "var(--gray-9)" }} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search properties, contacts, groups..."
            className="flex-1 h-12 text-[15px] border-0 outline-none bg-transparent"
          />
          <kbd className="text-[11px] px-1.5 py-0.5 rounded border" style={{ borderColor: "var(--gray-6)", color: "var(--gray-8)" }}>
            esc
          </kbd>
        </div>

        {/* Results */}
        {results.length > 0 && (
          <div className="max-h-80 overflow-y-auto py-2">
            {results.map((r, i) => (
              <div
                key={`${r.type}-${r.id}`}
                className="flex items-center gap-3 px-4 py-2 cursor-pointer"
                style={{
                  background: i === selectedIndex ? "var(--gray-a3)" : "transparent",
                }}
                onClick={() => navigateTo(r)}
                onMouseEnter={() => setSelectedIndex(i)}
              >
                <Badge size="1" variant="soft" color={typeColor(r.type)} style={{ minWidth: 60, textAlign: "center" }}>
                  {r.type}
                </Badge>
                <div className="flex-1 min-w-0">
                  <Text size="2" weight="medium" className="block truncate">{r.title}</Text>
                  {r.subtitle && (
                    <Text size="1" className="block truncate" style={{ color: "var(--gray-9)" }}>{r.subtitle}</Text>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {query && results.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <Text size="2" style={{ color: "var(--gray-9)" }}>No results for "{query}"</Text>
          </div>
        )}

        {!query && (
          <div className="flex items-center justify-center py-8">
            <Text size="2" style={{ color: "var(--gray-8)" }}>Start typing to search...</Text>
          </div>
        )}
      </div>
    </>
  );
}
