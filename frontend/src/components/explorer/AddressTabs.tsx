import { Link, useLocation } from "react-router-dom";
import { Text } from "@radix-ui/themes";

/**
 * Sub-tab bar for the Addresses section. Renders below ExplorerTabs.
 *   Roots | Bases
 *
 * Roots is matched by /explorer/addresses/roots* AND the bare /explorer/addresses
 * (because that path redirects to /explorer/addresses/roots).
 * Bases is matched by /explorer/addresses/bases*.
 */
export default function AddressTabs() {
  const location = useLocation();
  const path = location.pathname;

  const subtabs: { label: string; href: string; matches: (p: string) => boolean }[] = [
    {
      label: "Roots",
      href: "/explorer/addresses/roots",
      matches: (p) =>
        p === "/explorer/addresses" ||
        p === "/explorer/addresses/" ||
        p.startsWith("/explorer/addresses/roots"),
    },
    {
      label: "Bases",
      href: "/explorer/addresses/bases",
      matches: (p) => p.startsWith("/explorer/addresses/bases"),
    },
  ];

  return (
    <div className="border-b border-[var(--gray-4)] mb-5">
      <div className="flex items-center gap-3 px-3 py-2"
           style={{ background: "var(--gray-2)" }}>
        <Text size="1" style={{ color: "var(--gray-9)" }}>Address level:</Text>
        {subtabs.map((t) => {
          const active = t.matches(path);
          return (
            <Link key={t.href} to={t.href}
                  className="text-[12px] no-underline"
                  style={{
                    color: active ? "var(--accent-11)" : "var(--gray-11)",
                    fontWeight: active ? 600 : 400,
                  }}>
              {t.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
