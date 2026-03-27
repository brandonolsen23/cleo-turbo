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
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n.toLocaleString()}`;
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
