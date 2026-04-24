import { Link, useLocation } from "react-router-dom";
import { Text } from "@radix-ui/themes";

/**
 * Top-level + Brands sub-tabs for the Explorer. Renders a two-row tab bar:
 *   Brands | Phones | Addresses | Contacts
 *   (when on Brands) → 1-gram | 2-gram | 3-gram
 */
export default function ExplorerTabs() {
  const location = useLocation();
  const path = location.pathname;

  const topTabs: { label: string; href: string; matches: (p: string) => boolean }[] = [
    { label: "Brands",    href: "/explorer/brands/1gram",   matches: (p) => p.startsWith("/explorer/brands") },
    { label: "Phones",    href: "/explorer/phones",         matches: (p) => p.startsWith("/explorer/phones") },
    { label: "Addresses", href: "/explorer/addresses",      matches: (p) => p.startsWith("/explorer/addresses") },
    { label: "Contacts",  href: "/explorer/contacts",       matches: (p) => p.startsWith("/explorer/contacts") },
  ];

  const brandSubtabs: { label: string; href: string; matches: (p: string) => boolean }[] = [
    { label: "1-gram", href: "/explorer/brands/1gram", matches: (p) => p.startsWith("/explorer/brands/1gram") },
    { label: "2-gram", href: "/explorer/brands/2gram", matches: (p) => p.startsWith("/explorer/brands/2gram") },
    { label: "3-gram", href: "/explorer/brands/3gram", matches: (p) => p.startsWith("/explorer/brands/3gram") },
  ];

  const onBrands = path.startsWith("/explorer/brands");

  return (
    <div className="border-b border-[var(--gray-4)] mb-5">
      <div className="flex items-center gap-1 px-1">
        {topTabs.map((t) => {
          const active = t.matches(path);
          return (
            <Link key={t.href} to={t.href}
                  className="px-3 py-2 text-[13px] no-underline border-b-2"
                  style={{
                    color: active ? "var(--accent-11)" : "var(--gray-11)",
                    borderColor: active ? "var(--accent-11)" : "transparent",
                    fontWeight: active ? 600 : 400,
                  }}>
              {t.label}
            </Link>
          );
        })}
      </div>
      {onBrands && (
        <div className="flex items-center gap-3 px-3 py-2"
             style={{ background: "var(--gray-2)" }}>
          <Text size="1" style={{ color: "var(--gray-9)" }}>Gram level:</Text>
          {brandSubtabs.map((t) => {
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
      )}
    </div>
  );
}
