import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ============================================================
// Currency
// ============================================================

export function formatCurrency(amount: number | null | undefined): string {
  if (amount == null || amount === 0) return "—";
  return amount.toLocaleString("en-CA", { style: "currency", currency: "CAD", minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

export function formatCompact(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`;
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n.toLocaleString()}`;
}

export function formatSf(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M sf`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(0)}k sf`;
  return `${Math.round(n).toLocaleString()} sf`;
}

/** Format a canonical address key (city|street_number|...|suite_number) for display. */
export function formatCanonicalAddress(canonical: string | null | undefined): string {
  if (!canonical) return "";
  const parts = canonical.split("|");
  if (parts.length !== 7) return canonical;
  const [city, num, name, suf, dir_, stype, snum] = parts;
  const street = [num, titleCase(name), titleCase(suf), titleCase(dir_)]
    .filter(Boolean)
    .join(" ");
  const cleanSnum = snum && /[a-z]/i.test(snum) ? titleCase(snum) : snum;
  const suite = cleanSnum
    ? `${stype === "po_box" ? "PO Box" : titleCase(stype)} ${cleanSnum}`
    : "";
  const cityPart = city ? titleCase(city) : "";
  return [street, suite, cityPart].filter(Boolean).join(", ");
}

/** Format a portfolio-size entry like "2.86M sf" or "24,881 units". */
export function formatPortfolioUnit(unit: string, total: number): string {
  if (unit === "sf") return formatSf(total);
  const compact =
    total >= 1_000_000 ? `${(total / 1_000_000).toFixed(2)}M` :
    total >= 10_000 ? `${(total / 1_000).toFixed(0)}k` :
    Math.round(total).toLocaleString();
  return `${compact} ${unit}`;
}

// ============================================================
// Ownership
// ============================================================

export function formatOwnership(years: number | null | undefined): string {
  if (years == null || years < 0) return "—";
  return `${years.toFixed(1)} yrs`;
}

export function computeOwnershipYears(saleDate: string | null | undefined): number | null {
  if (!saleDate) return null;
  const d = new Date(saleDate + "T00:00:00");
  if (isNaN(d.getTime())) return null;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  return Math.round((diffMs / (365.25 * 24 * 60 * 60 * 1000)) * 10) / 10;
}

// ============================================================
// Date
// ============================================================

export function formatDate(date: string | null | undefined): string {
  if (!date) return "—";
  const d = new Date(date + "T00:00:00");
  if (isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ============================================================
// Phone
// ============================================================

export function formatPhone(phone: string | null | undefined): string {
  if (!phone) return "—";
  const digits = phone.replace(/\D/g, "");
  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  if (digits.length === 11 && digits[0] === "1") {
    return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  return phone;
}

export function formatMailingAddress(addr: { display?: string | null; city?: string | null; province?: string | null; postal?: string | null } | null | undefined): string | null {
  if (!addr) return null;
  const parts: string[] = [];
  if (addr.display) parts.push(addr.display);
  if (addr.city) parts.push(addr.city);
  if (addr.province) parts.push(addr.province);
  if (addr.postal) parts.push(addr.postal);
  return parts.length > 0 ? parts.join(", ") : null;
}

// ============================================================
// Text
// ============================================================

export function titleCase(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .toLowerCase()
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

const STREET_SUFFIXES: Record<string, string> = {
  STREET: "St", AVENUE: "Ave", ROAD: "Rd", DRIVE: "Dr",
  BOULEVARD: "Blvd", CRESCENT: "Cres", COURT: "Crt", PLACE: "Pl",
  LANE: "Ln", CIRCLE: "Cir", TRAIL: "Trl", TERRACE: "Terr",
  HIGHWAY: "Hwy", PARKWAY: "Pkwy", CONCESSION: "Con",
};

const DIRECTIONS: Record<string, string> = {
  NORTH: "N", SOUTH: "S", EAST: "E", WEST: "W",
  NORTHEAST: "NE", NORTHWEST: "NW", SOUTHEAST: "SE", SOUTHWEST: "SW",
};

export function formatStreet(address: string | null | undefined): string {
  if (!address) return "";
  let result = titleCase(address);
  for (const [full, abbr] of Object.entries(STREET_SUFFIXES)) {
    result = result.replace(new RegExp(`\\b${titleCase(full)}\\b`, "g"), abbr);
  }
  for (const [full, abbr] of Object.entries(DIRECTIONS)) {
    result = result.replace(new RegExp(`\\b${titleCase(full)}\\b`, "g"), abbr);
  }
  return result;
}

// ============================================================
// Numbers
// ============================================================

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

// ============================================================
// Asset Classes
// ============================================================

const ASSET_CLASS_LABELS: Record<string, string> = {
  retail: "Retail",
  industrial: "Industrial",
  multifamily: "Multifamily",
  office: "Office",
  land: "Land",
  agricultural: "Agricultural",
  mixed_use: "Mixed Use",
  hospitality: "Hospitality",
};

export function assetClassLabel(id: string | null | undefined): string {
  if (!id) return "—";
  return ASSET_CLASS_LABELS[id] || titleCase(id.replace(/_/g, " "));
}
