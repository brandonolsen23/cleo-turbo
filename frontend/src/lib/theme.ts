// ============================================================
// Cleo Turbo Design System
// ============================================================

export type RadixColor =
  | "jade" | "orange" | "blue" | "cyan" | "lime" | "sky"
  | "amber" | "violet" | "pink" | "gray" | "brown" | "tomato"
  | "plum" | "indigo" | "iris" | "red" | "green"
  | "slate" | "gold" | "bronze" | "mint" | "teal" | "crimson"
  | "ruby" | "grass" | "mauve" | "sand";

// ============================================================
// Property Type Colors
// ============================================================

const PROPERTY_TYPE_COLORS: Record<string, RadixColor> = {
  retail: "jade",
  industrial: "orange",
  multifamily: "blue",
  office: "cyan",
  farm: "lime",
  "res-land": "sky",
  "comm-ind-land": "amber",
  "hotel-motel": "violet",
  "restaurant-bar": "pink",
  "other-bldg": "gray",
  "other-land": "brown",
};

export function propertyTypeColor(type: string): RadixColor {
  return PROPERTY_TYPE_COLORS[type] ?? "gray";
}

export function propertyTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    retail: "Retail",
    industrial: "Industrial",
    multifamily: "Multifamily",
    office: "Office",
    farm: "Farm",
    "res-land": "Residential Land",
    "comm-ind-land": "C/I Land",
    "hotel-motel": "Hotel/Motel",
    "restaurant-bar": "Restaurant/Bar",
    "other-bldg": "Other Building",
    "other-land": "Other Land",
  };
  return labels[type] ?? type;
}

// ============================================================
// Tenant / Brand Category Colors
// ============================================================

const CATEGORY_COLORS: Record<string, RadixColor> = {
  grocery: "lime",
  qsr: "orange",
  "big-box retail": "blue",
  "specialty retail": "plum",
  "discount retail": "amber",
  "full-service": "violet",
  "take-out": "pink",
  automotive: "tomato",
  "financial services": "cyan",
  fuel: "indigo",
};

export function categoryColor(category: string | null | undefined): RadixColor {
  if (!category) return "gray";
  return CATEGORY_COLORS[category.toLowerCase()] ?? "gray";
}

// ============================================================
// Asset Class Colors (for mini-maps and charts)
// ============================================================

const ASSET_CLASS_COLORS: Record<string, RadixColor> = {
  retail: "jade",
  industrial: "blue",
  multifamily: "amber",
  office: "violet",
  land: "gray",
  agricultural: "brown",
  mixed_use: "teal",
  hospitality: "tomato",
};

export function assetClassColor(assetClass: string): RadixColor {
  return ASSET_CLASS_COLORS[assetClass] ?? "gray";
}

// ============================================================
// Chart Colors
// ============================================================

export const CHART_COLORS = {
  primary: ["var(--jade-11)", "var(--jade-9)", "var(--jade-7)", "var(--jade-4)"],
  accent: "var(--jade-9)",
  positive: "var(--green-11)",
  negative: "var(--red-11)",
  neutral: "var(--gray-8)",
};

// ============================================================
// Deal Stage Colors
// ============================================================

export const DEAL_STAGE_COLORS: Record<string, RadixColor> = {
  long_shot: "gray",
  priority_deal: "blue",
  mandate: "blue",
  viable_deal: "amber",
  in_negotiation: "amber",
  under_contract: "orange",
  firm: "jade",
  closed: "jade",
  lost: "red",
};

export const DEAL_STAGES = [
  "long_shot",
  "priority_deal",
  "mandate",
  "viable_deal",
  "in_negotiation",
  "under_contract",
  "firm",
  "closed",
  "lost",
] as const;

export function dealStageLabel(stage: string): string {
  const labels: Record<string, string> = {
    long_shot: "Long Shot",
    priority_deal: "Priority Deal",
    mandate: "Mandate",
    viable_deal: "Viable Deal",
    in_negotiation: "In Negotiation",
    under_contract: "Under Contract",
    firm: "Firm",
    closed: "Closed",
    lost: "Lost",
  };
  return labels[stage] ?? stage;
}

// ============================================================
// Radix Hex Table (sRGB)
//
// Mapbox GL paint expressions cannot use CSS variables, and
// getComputedStyle() returns Display-P3 on Apple Silicon which
// Mapbox rejects. This static table provides sRGB hex values
// for all Radix colors at each step.
// ============================================================

const RADIX_HEX: Record<string, string> = {
  // Jade
  "jade-1": "#f2fcf7", "jade-2": "#e7f9f0", "jade-3": "#c7f2de",
  "jade-4": "#a4e8ca", "jade-5": "#82dbb5", "jade-6": "#5ecc9e",
  "jade-7": "#3bb68a", "jade-8": "#2da07a", "jade-9": "#29a383",
  "jade-10": "#248f75", "jade-11": "#1a7a63", "jade-12": "#1d3b30",

  // Orange
  "orange-1": "#fefcfb", "orange-2": "#fff7ed", "orange-3": "#ffefd6",
  "orange-4": "#ffdfb5", "orange-5": "#ffd19a", "orange-6": "#ffc182",
  "orange-7": "#f5a862", "orange-8": "#e69036", "orange-9": "#f76b15",
  "orange-10": "#ef5f00", "orange-11": "#cc4e00", "orange-12": "#582d1d",

  // Blue
  "blue-1": "#fbfdff", "blue-2": "#f4faff", "blue-3": "#e6f4fe",
  "blue-4": "#d5efff", "blue-5": "#c2e5ff", "blue-6": "#acd8fc",
  "blue-7": "#8ec8f6", "blue-8": "#5eb1ef", "blue-9": "#0090ff",
  "blue-10": "#0588f0", "blue-11": "#0d74ce", "blue-12": "#113264",

  // Cyan
  "cyan-1": "#fafdfe", "cyan-2": "#f2fafb", "cyan-3": "#def7f9",
  "cyan-4": "#caf1f6", "cyan-5": "#b5e9f0", "cyan-6": "#9ddde7",
  "cyan-7": "#7dcedc", "cyan-8": "#3db9cf", "cyan-9": "#00a2c7",
  "cyan-10": "#0797b9", "cyan-11": "#107d98", "cyan-12": "#0d3c48",

  // Lime
  "lime-1": "#fcfdfa", "lime-2": "#f8faf3", "lime-3": "#eef6d6",
  "lime-4": "#e2f0bd", "lime-5": "#d3e7a6", "lime-6": "#c2da91",
  "lime-7": "#abc978", "lime-8": "#8db654", "lime-9": "#bdee63",
  "lime-10": "#b0e64c", "lime-11": "#5c7c2f", "lime-12": "#37401c",

  // Sky
  "sky-1": "#f9feff", "sky-2": "#f1fafd", "sky-3": "#e1f6fd",
  "sky-4": "#d1f0fa", "sky-5": "#bee7f5", "sky-6": "#a9daed",
  "sky-7": "#8dcae3", "sky-8": "#60b3d7", "sky-9": "#7ce2fe",
  "sky-10": "#74daf8", "sky-11": "#00749e", "sky-12": "#1d3e56",

  // Amber
  "amber-1": "#fefdfb", "amber-2": "#fefbe9", "amber-3": "#fff7c2",
  "amber-4": "#ffee9c", "amber-5": "#fbe577", "amber-6": "#f3d768",
  "amber-7": "#e9c162", "amber-8": "#e2a336", "amber-9": "#ffc53d",
  "amber-10": "#ffba18", "amber-11": "#ab6400", "amber-12": "#4f3422",

  // Violet
  "violet-1": "#fdfcfe", "violet-2": "#faf8ff", "violet-3": "#f4f0fe",
  "violet-4": "#ebe4ff", "violet-5": "#e1d9ff", "violet-6": "#d4cafe",
  "violet-7": "#c2b5f5", "violet-8": "#aa99ec", "violet-9": "#6e56cf",
  "violet-10": "#654dc4", "violet-11": "#6550b9", "violet-12": "#2f265f",

  // Pink
  "pink-1": "#fffcfe", "pink-2": "#fef7fb", "pink-3": "#fee9f5",
  "pink-4": "#fbdcef", "pink-5": "#f6cee7", "pink-6": "#efbfdd",
  "pink-7": "#e5a8cf", "pink-8": "#d985bc", "pink-9": "#d6409f",
  "pink-10": "#cf3897", "pink-11": "#c2298a", "pink-12": "#651249",

  // Gray (Slate)
  "gray-1": "#fcfcfd", "gray-2": "#f9f9fb", "gray-3": "#f0f0f3",
  "gray-4": "#e8e8ec", "gray-5": "#e0e1e6", "gray-6": "#d9d9e0",
  "gray-7": "#cdced6", "gray-8": "#b9bbc6", "gray-9": "#8b8d98",
  "gray-10": "#80838d", "gray-11": "#60646c", "gray-12": "#1c2024",

  // Brown
  "brown-1": "#fefdfc", "brown-2": "#fcf9f6", "brown-3": "#f6eee7",
  "brown-4": "#f0e4d9", "brown-5": "#ebdaca", "brown-6": "#e4cdb7",
  "brown-7": "#dcbc9f", "brown-8": "#cea37e", "brown-9": "#ad7f58",
  "brown-10": "#a07553", "brown-11": "#815e46", "brown-12": "#3e332e",

  // Tomato
  "tomato-1": "#fffcfc", "tomato-2": "#fff8f7", "tomato-3": "#feebe7",
  "tomato-4": "#ffdcd3", "tomato-5": "#ffcdc2", "tomato-6": "#fdbdaf",
  "tomato-7": "#f5a898", "tomato-8": "#ec8e7b", "tomato-9": "#e54d2e",
  "tomato-10": "#dd4425", "tomato-11": "#d13415", "tomato-12": "#5c271f",

  // Plum
  "plum-1": "#fefcff", "plum-2": "#fdf7fd", "plum-3": "#fbebfb",
  "plum-4": "#f7def8", "plum-5": "#f2d1f3", "plum-6": "#e9c2ec",
  "plum-7": "#deade3", "plum-8": "#cf91d8", "plum-9": "#ab4aba",
  "plum-10": "#a144af", "plum-11": "#953ea3", "plum-12": "#53195d",

  // Indigo
  "indigo-1": "#fdfdfe", "indigo-2": "#f7f9ff", "indigo-3": "#edf2fe",
  "indigo-4": "#e1e9ff", "indigo-5": "#d2deff", "indigo-6": "#c1d0ff",
  "indigo-7": "#abbdf9", "indigo-8": "#8da4ef", "indigo-9": "#3e63dd",
  "indigo-10": "#3358d4", "indigo-11": "#3a5bc7", "indigo-12": "#1f2d5c",

  // Red
  "red-1": "#fffcfc", "red-2": "#fff7f7", "red-3": "#feebec",
  "red-4": "#ffdbdc", "red-5": "#ffcdce", "red-6": "#fdbdbe",
  "red-7": "#f4a9aa", "red-8": "#eb8e90", "red-9": "#e5484d",
  "red-10": "#dc3e42", "red-11": "#ce2c31", "red-12": "#641723",

  // Green
  "green-1": "#fbfefc", "green-2": "#f4fbf6", "green-3": "#e6f6eb",
  "green-4": "#d6f1df", "green-5": "#c4e8d1", "green-6": "#adddc0",
  "green-7": "#8eceaa", "green-8": "#5bb98b", "green-9": "#30a46c",
  "green-10": "#2b9a66", "green-11": "#218358", "green-12": "#193b2d",

  // Iris
  "iris-1": "#fdfdff", "iris-2": "#f8f8ff", "iris-3": "#f0f1fe",
  "iris-4": "#e6e7ff", "iris-5": "#dadcff", "iris-6": "#cbcdff",
  "iris-7": "#b8baf8", "iris-8": "#9b9ef0", "iris-9": "#5b5bd6",
  "iris-10": "#5151cd", "iris-11": "#5753c6", "iris-12": "#272962",
};

export function getRadixHex(color: RadixColor | string, step: number): string {
  return RADIX_HEX[`${color}-${step}`] ?? "#8b8d98";
}

// ============================================================
// Sell Opportunity Status Colors
// ============================================================

export const SELL_OPP_STATUS_COLORS: Record<string, RadixColor> = {
  active: "jade",
  on_hold: "amber",
  stale: "tomato",
  matched: "blue",
  closed_won: "green",
  closed_lost: "red",
};

export function sellOppStatusColor(status: string): RadixColor {
  return SELL_OPP_STATUS_COLORS[status] ?? "gray";
}

export function sellOppStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: "Active",
    on_hold: "On Hold",
    stale: "Stale",
    matched: "Matched",
    closed_won: "Closed Won",
    closed_lost: "Closed Lost",
  };
  return labels[status] ?? status;
}

// ============================================================
// Buy Mandate Status Colors
// ============================================================

export const BUY_MANDATE_STATUS_COLORS: Record<string, RadixColor> = {
  active: "jade",
  on_hold: "amber",
  stale: "tomato",
  fulfilled: "blue",
};

export function buyMandateStatusColor(status: string): RadixColor {
  return BUY_MANDATE_STATUS_COLORS[status] ?? "gray";
}

export function buyMandateStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: "Active",
    on_hold: "On Hold",
    stale: "Stale",
    fulfilled: "Fulfilled",
  };
  return labels[status] ?? status;
}

// ============================================================
// Activity Type Helpers
// ============================================================

export const ACTIVITY_TYPE_COLORS: Record<string, RadixColor> = {
  call: "blue",
  email: "violet",
  meeting: "jade",
  note: "gray",
};

export function activityTypeColor(type: string): RadixColor {
  return ACTIVITY_TYPE_COLORS[type] ?? "gray";
}

export function activityTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    call: "Call",
    email: "Email",
    meeting: "Meeting",
    note: "Note",
  };
  return labels[type] ?? type;
}

// Build a Mapbox GL match expression for property type → color
export function propertyTypeMatchExpression(step: number = 9): unknown[] {
  const expr: unknown[] = ["match", ["get", "primary_property_type"]];
  for (const [type, color] of Object.entries(PROPERTY_TYPE_COLORS)) {
    expr.push(type, getRadixHex(color, step));
  }
  expr.push(getRadixHex("gray", step)); // fallback
  return expr;
}
