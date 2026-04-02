import { useLocation } from "react-router-dom";
import { Text } from "@radix-ui/themes";
import { MagnifyingGlass } from "@phosphor-icons/react";

const PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/properties": "Properties",
  "/transactions": "Transactions",
  "/contacts": "Contacts",
  "/groups": "Groups",
  "/map": "Map",
  "/deals": "Deals",
  "/lists": "Lists",
  "/pipeline": "Pipeline Inspector",
  "/data-quality": "Data Quality",
  "/admin": "Admin",
};

function getPageTitle(pathname: string): string {
  // Exact match first
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  // Detail pages
  if (pathname.startsWith("/properties/")) return "Property Detail";
  if (pathname.startsWith("/transactions/")) return "Transaction Detail";
  if (pathname.startsWith("/contacts/")) return "Contact Detail";
  if (pathname.startsWith("/groups/")) return "Group Detail";
  if (pathname.startsWith("/lists/")) return "List Detail";
  if (pathname.startsWith("/pipeline/trace/")) return "RT Trace";
  if (pathname.startsWith("/pipeline/")) return "Pipeline Stage";
  return "";
}

export default function Header() {
  const location = useLocation();
  const pageTitle = getPageTitle(location.pathname);

  const triggerSearch = () => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
  };

  return (
    <div className="app-header flex items-center justify-between px-6 border-b border-[var(--gray-4)]" style={{ background: "white" }}>
      <div className="flex items-center">
        <Text size="2" weight="medium" style={{ color: "var(--gray-12)" }}>Cleo</Text>
        {pageTitle && (
          <>
            <div className="w-px h-4 mx-3" style={{ background: "var(--gray-6)" }} />
            <Text size="2" style={{ color: "var(--gray-9)" }}>{pageTitle}</Text>
          </>
        )}
      </div>

      <button
        onClick={triggerSearch}
        className="flex items-center gap-2 h-8 px-3 rounded-lg border transition-colors hover:border-[var(--gray-8)]"
        style={{ borderColor: "var(--gray-6)", background: "var(--gray-2)" }}
      >
        <MagnifyingGlass size={14} style={{ color: "var(--gray-9)" }} />
        <Text size="1" style={{ color: "var(--gray-8)" }}>Search...</Text>
        <kbd className="text-[10px] px-1 py-0.5 rounded border ml-2" style={{ borderColor: "var(--gray-5)", color: "var(--gray-8)" }}>
          ⌘K
        </kbd>
      </button>
    </div>
  );
}
