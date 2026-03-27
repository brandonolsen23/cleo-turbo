import { useState, useMemo, useRef, useLayoutEffect, useCallback } from "react";
import { Text } from "@radix-ui/themes";

// ============================================================
// Types
// ============================================================

interface TraceData {
  rt_id: string;
  classifications: { source_folder: string; position: number }[];
  stages: Record<string, any>;
}

interface Connection {
  from: string; // "stage:field.path"
  to: string;
  type: "pass" | "parse" | "split" | "extract" | "restructure" | "enrich";
}

interface PathData {
  d: string;
  color: string;
  from: string;
  to: string;
  type: string;
}

// ============================================================
// Connection colors
// ============================================================

const TYPE_COLORS: Record<string, string> = {
  pass: "#b9bbc6",        // gray-8
  parse: "#0d74ce",       // blue-11
  split: "#ab6400",       // amber-11
  extract: "#6550b9",     // violet-11
  restructure: "#1a7a63", // jade-11
  enrich: "#107d98",      // cyan-11
};

const TYPE_LABELS: Record<string, string> = {
  pass: "Pass-through",
  parse: "Parsed",
  split: "Split",
  extract: "Extracted",
  restructure: "Restructured",
  enrich: "Enriched",
};

// ============================================================
// Connection mapping — every field-to-field link
// ============================================================

const CONNECTIONS: Connection[] = [
  // ── Assembled → Classified ──
  { from: "assembled:detail.header.date_text",           to: "classified:header.sale_date",           type: "parse" },
  { from: "assembled:detail.header.price_text",          to: "classified:header.sale_price",          type: "parse" },
  { from: "assembled:detail.header.city_region",         to: "classified:header.city",                type: "split" },
  { from: "assembled:detail.header.city_region",         to: "classified:header.region",              type: "split" },
  { from: "assembled:detail.header.address_lines",       to: "classified:header.address_entries",     type: "restructure" },
  { from: "assembled:detail.header.note",                to: "classified:header.transaction_note",    type: "pass" },
  { from: "assembled:detail.transferor.party_lines",     to: "classified:seller.parties",             type: "restructure" },
  { from: "assembled:detail.transferor.contact_lines",   to: "classified:seller.contacts",            type: "extract" },
  { from: "assembled:detail.transferor.contact_lines",   to: "classified:seller.phone",               type: "extract" },
  { from: "assembled:detail.transferor.contact_lines",   to: "classified:seller.address.lines",       type: "extract" },
  { from: "assembled:detail.transferor.contact_lines",   to: "classified:seller.address.city",        type: "extract" },
  { from: "assembled:detail.transferor.contact_lines",   to: "classified:seller.address.province",    type: "extract" },
  { from: "assembled:detail.transferor.contact_lines",   to: "classified:seller.address.postal",      type: "extract" },
  { from: "assembled:detail.transferor.contact_lines",   to: "classified:seller.address.country",     type: "extract" },
  { from: "assembled:detail.transferor.trade_name",      to: "classified:seller.trade_name",          type: "pass" },
  { from: "assembled:detail.transferee.party_lines",     to: "classified:buyer.parties",              type: "restructure" },
  { from: "assembled:detail.transferee.contact_lines",   to: "classified:buyer.contacts",             type: "extract" },
  { from: "assembled:detail.transferee.contact_lines",   to: "classified:buyer.phone",                type: "extract" },
  { from: "assembled:detail.transferee.contact_lines",   to: "classified:buyer.address.lines",        type: "extract" },
  { from: "assembled:detail.transferee.contact_lines",   to: "classified:buyer.address.city",         type: "extract" },
  { from: "assembled:detail.transferee.contact_lines",   to: "classified:buyer.address.province",     type: "extract" },
  { from: "assembled:detail.transferee.contact_lines",   to: "classified:buyer.address.postal",       type: "extract" },
  { from: "assembled:detail.transferee.contact_lines",   to: "classified:buyer.address.country",      type: "extract" },
  { from: "assembled:detail.transferee.trade_name",      to: "classified:buyer.trade_name",           type: "pass" },
  { from: "assembled:detail.site_lines",                 to: "classified:site.pin",                   type: "extract" },
  { from: "assembled:detail.site_lines",                 to: "classified:site.acreage",               type: "extract" },
  { from: "assembled:detail.site_lines",                 to: "classified:site.legal_description",     type: "extract" },
  { from: "assembled:detail.arn_text",                   to: "classified:arn",                        type: "pass" },
  { from: "assembled:detail.consideration_lines",        to: "classified:consideration.cash",         type: "extract" },
  { from: "assembled:detail.consideration_lines",        to: "classified:consideration.debt",         type: "extract" },
  { from: "assembled:detail.consideration_lines",        to: "classified:consideration.charges",      type: "extract" },
  { from: "assembled:detail.broker_lines",               to: "classified:broker.brokers",             type: "restructure" },
  { from: "assembled:detail.photos.street_photo_urls",   to: "classified:photos.street_photo_urls",   type: "pass" },
  { from: "assembled:detail.photos.aerial_photo_urls",   to: "classified:photos.aerial_photo_urls",   type: "pass" },

  // ── Classified → Addresses (enrichment — address expansion) ──
  // NOTE: address array connections are built dynamically in buildDynamicConnections()
  { from: "classified:seller.address.lines",    to: "addresses:seller.address.display",              type: "enrich" },
  { from: "classified:seller.address.city",     to: "addresses:seller.address.city",                 type: "pass" },
  { from: "classified:seller.address.province", to: "addresses:seller.address.province",             type: "pass" },
  { from: "classified:seller.address.postal",   to: "addresses:seller.address.postal",               type: "pass" },
  { from: "classified:seller.address.lines",    to: "addresses:seller.address.components",           type: "enrich" },
  { from: "classified:seller.address.lines",    to: "addresses:seller.address.geocode_string",       type: "enrich" },
  { from: "classified:buyer.address.lines",     to: "addresses:buyer.address.display",               type: "enrich" },
  { from: "classified:buyer.address.city",      to: "addresses:buyer.address.city",                  type: "pass" },
  { from: "classified:buyer.address.province",  to: "addresses:buyer.address.province",              type: "pass" },
  { from: "classified:buyer.address.postal",    to: "addresses:buyer.address.postal",                type: "pass" },
  { from: "classified:buyer.address.lines",     to: "addresses:buyer.address.components",            type: "enrich" },
  { from: "classified:buyer.address.lines",     to: "addresses:buyer.address.geocode_string",        type: "enrich" },
  { from: "classified:site.pin",                to: "addresses:pin.original",                        type: "enrich" },
  { from: "classified:site.pin",                to: "addresses:pin.display",                         type: "enrich" },
  { from: "classified:site.pin",                to: "addresses:pin.api_format",                      type: "enrich" },
  { from: "classified:arn",                     to: "addresses:arn.original",                        type: "enrich" },
  { from: "classified:arn",                     to: "addresses:arn.display",                         type: "enrich" },
  { from: "classified:arn",                     to: "addresses:arn.api_format",                      type: "enrich" },

  // ── Addresses → Clean ──
  // NOTE: address array connections are built dynamically in buildDynamicConnections()
  { from: "addresses:seller.address.display",        to: "clean:seller.address.display",        type: "pass" },
  { from: "addresses:seller.address.city",           to: "clean:seller.address.city",           type: "pass" },
  { from: "addresses:seller.address.province",       to: "clean:seller.address.province",       type: "pass" },
  { from: "addresses:seller.address.postal",         to: "clean:seller.address.postal",         type: "pass" },
  { from: "addresses:seller.address.components",     to: "clean:seller.address.components",     type: "pass" },
  { from: "addresses:seller.address.geocode_string", to: "clean:seller.address.geocode_string", type: "pass" },
  { from: "addresses:buyer.address.display",         to: "clean:buyer.address.display",         type: "pass" },
  { from: "addresses:buyer.address.city",            to: "clean:buyer.address.city",            type: "pass" },
  { from: "addresses:buyer.address.province",        to: "clean:buyer.address.province",        type: "pass" },
  { from: "addresses:buyer.address.postal",          to: "clean:buyer.address.postal",          type: "pass" },
  { from: "addresses:buyer.address.components",      to: "clean:buyer.address.components",      type: "pass" },
  { from: "addresses:buyer.address.geocode_string",  to: "clean:buyer.address.geocode_string",  type: "pass" },
  { from: "addresses:pin.original",    to: "clean:site.pin.original",    type: "pass" },
  { from: "addresses:pin.display",     to: "clean:site.pin.display",     type: "pass" },
  { from: "addresses:pin.api_format",  to: "clean:site.pin.api_format",  type: "pass" },
  { from: "addresses:arn.original",    to: "clean:site.arn.original",    type: "pass" },
  { from: "addresses:arn.display",     to: "clean:site.arn.display",     type: "pass" },
  { from: "addresses:arn.api_format",  to: "clean:site.arn.api_format",  type: "pass" },

  // ── Classified → Clean (pass-through, skipping addresses) ──
  { from: "classified:header.sale_date",          to: "clean:transaction.sale_date",        type: "pass" },
  { from: "classified:header.sale_price",         to: "clean:transaction.sale_price",       type: "pass" },
  { from: "classified:header.city",               to: "clean:transaction.city",             type: "pass" },
  { from: "classified:header.region",             to: "clean:transaction.region",           type: "pass" },
  { from: "classified:header.transaction_note",   to: "clean:transaction.transaction_note", type: "pass" },
  { from: "classified:seller.parties",            to: "clean:seller.parties",               type: "pass" },
  { from: "classified:seller.phone",              to: "clean:seller.phone",                 type: "pass" },
  { from: "classified:seller.contacts",           to: "clean:seller.contacts",              type: "pass" },
  { from: "classified:seller.trade_name",         to: "clean:seller.trade_name",            type: "pass" },
  { from: "classified:seller.address.country",   to: "clean:seller.address.country",      type: "pass" },
  { from: "classified:buyer.parties",             to: "clean:buyer.parties",                type: "pass" },
  { from: "classified:buyer.phone",               to: "clean:buyer.phone",                 type: "pass" },
  { from: "classified:buyer.contacts",            to: "clean:buyer.contacts",               type: "pass" },
  { from: "classified:buyer.trade_name",          to: "clean:buyer.trade_name",             type: "pass" },
  { from: "classified:buyer.address.country",    to: "clean:buyer.address.country",       type: "pass" },
  { from: "classified:site.acreage",              to: "clean:site.acreage",                 type: "pass" },
  { from: "classified:site.legal_description",    to: "clean:site.legal_description",       type: "pass" },
  { from: "classified:consideration.cash",        to: "clean:consideration.cash",           type: "pass" },
  { from: "classified:consideration.debt",        to: "clean:consideration.debt",           type: "pass" },
  { from: "classified:consideration.charges",     to: "clean:consideration.charges",        type: "pass" },
  { from: "classified:broker.brokers",            to: "clean:broker.brokers",               type: "pass" },
  { from: "classified:photos.street_photo_urls",  to: "clean:photos.street_photo_urls",     type: "pass" },
  { from: "classified:photos.aerial_photo_urls",  to: "clean:photos.aerial_photo_urls",     type: "pass" },

  // ── Parcel Links → Clean ──
  { from: "parcel_links:resolved_arn",  to: "clean:parcel.resolved_arn",  type: "pass" },
  { from: "parcel_links:method",        to: "clean:parcel.method",        type: "pass" },
  { from: "parcel_links:parcel_file",   to: "clean:parcel.parcel_file",   type: "pass" },
];

/**
 * Build dynamic connections for array fields (addresses, etc.)
 * based on the actual data in the trace. This replaces hardcoded
 * [0], [1] indices — it generates connections for however many
 * items actually exist in the record.
 */
function buildDynamicConnections(trace: TraceData): Connection[] {
  const dynamic: Connection[] = [];
  const addrSubFields = ["display", "components", "geocode_string", "geocodable"];

  // Get addresses stage data to count actual addresses
  const addrData = getStageRecord(trace, "addresses");
  const addrCount = addrData?.property?.addresses?.length ?? 0;

  for (let i = 0; i < addrCount; i++) {
    // Classified address_entries → Addresses property.addresses[i]
    for (const sub of addrSubFields) {
      dynamic.push({ from: "classified:header.address_entries", to: `addresses:property.addresses[${i}].${sub}`, type: "enrich" });
    }
    // Addresses property.addresses[i] → Clean property.addresses[i]
    for (const sub of addrSubFields) {
      dynamic.push({ from: `addresses:property.addresses[${i}].${sub}`, to: `clean:property.addresses[${i}].${sub}`, type: "pass" });
    }
  }

  // If no addresses exist, still connect the entry point
  if (addrCount === 0) {
    dynamic.push({ from: "classified:header.address_entries", to: "addresses:property.addresses", type: "enrich" });
  }

  return dynamic;
}

// ============================================================
// Stage node field definitions
// ============================================================

interface FieldDef {
  id: string;    // unique field id for data-field-id attribute
  label: string; // display label
  path: string;  // dot-path to extract value from stage data
  section?: string;
}

/**
 * Build field definitions dynamically from the actual record data.
 * Arrays (addresses, parties, contacts, charges) are expanded into
 * individual rows so every item is visible and traceable.
 */
function stageFields(stage: string, data: any): FieldDef[] {
  const s = (path: string, label?: string): FieldDef => ({
    id: `${stage}:${path}`,
    label: label || path.split(".").pop()!,
    path,
  });

  // Helper: expand an array field into per-item rows with sub-fields
  function expandArray(basePath: string, subFields: string[], sectionLabel: string, itemLabel: string): FieldDef[] {
    const arr = getNestedValue(data, basePath);
    if (!Array.isArray(arr) || arr.length === 0) {
      return [{ ...s(basePath, `${itemLabel} (empty)`), section: sectionLabel }];
    }
    const fields: FieldDef[] = [];
    for (let i = 0; i < arr.length; i++) {
      const prefix = arr.length > 1 ? `${itemLabel} ${i + 1}` : itemLabel;
      for (let j = 0; j < subFields.length; j++) {
        const sub = subFields[j];
        const field = s(`${basePath}[${i}].${sub}`, `${prefix} ${sub}`);
        if (j === 0 && i === 0) field.section = sectionLabel;
        else if (j === 0 && i > 0) field.section = `${sectionLabel} (${i + 1})`;
        fields.push(field);
      }
    }
    return fields;
  }

  switch (stage) {
    case "assembled": return [
      { ...s("detail.header.date_text", "date_text"), section: "Header" },
      s("detail.header.price_text", "price_text"),
      s("detail.header.city_region", "city_region"),
      s("detail.header.address_lines", "address_lines"),
      s("detail.header.note", "note"),
      { ...s("detail.transferor.party_lines", "party_lines"), section: "Seller" },
      s("detail.transferor.contact_lines", "contact_lines"),
      s("detail.transferor.trade_name", "trade_name"),
      { ...s("detail.transferee.party_lines", "party_lines"), section: "Buyer" },
      s("detail.transferee.contact_lines", "contact_lines"),
      s("detail.transferee.trade_name", "trade_name"),
      { ...s("detail.site_lines", "site_lines"), section: "Site" },
      s("detail.arn_text", "arn_text"),
      { ...s("detail.consideration_lines", "consideration_lines"), section: "Financial" },
      s("detail.broker_lines", "broker_lines"),
      { ...s("detail.photos.street_photo_urls", "street_photos"), section: "Media" },
      s("detail.photos.aerial_photo_urls", "aerial_photos"),
    ];
    case "classified": return [
      { ...s("header.sale_date"), section: "Header" },
      s("header.sale_price"),
      s("header.city"),
      s("header.region"),
      s("header.address_entries"),
      s("header.transaction_note"),
      { ...s("seller.parties"), section: "Seller" },
      s("seller.contacts"),
      s("seller.phone"),
      s("seller.trade_name"),
      s("seller.address.lines", "addr lines"),
      s("seller.address.city", "addr city"),
      s("seller.address.province", "addr province"),
      s("seller.address.postal", "addr postal"),
      s("seller.address.country", "addr country"),
      { ...s("buyer.parties"), section: "Buyer" },
      s("buyer.contacts"),
      s("buyer.phone"),
      s("buyer.trade_name"),
      s("buyer.address.lines", "addr lines"),
      s("buyer.address.city", "addr city"),
      s("buyer.address.province", "addr province"),
      s("buyer.address.postal", "addr postal"),
      s("buyer.address.country", "addr country"),
      { ...s("site.pin"), section: "Site" },
      s("site.acreage"),
      s("site.legal_description"),
      s("arn"),
      { ...s("consideration.cash"), section: "Financial" },
      s("consideration.debt"),
      s("consideration.charges"),
      s("broker.brokers"),
      { ...s("photos.street_photo_urls"), section: "Media" },
      s("photos.aerial_photo_urls"),
    ];
    case "addresses": return [
      ...expandArray("property.addresses", ["display", "components", "geocode_string", "geocodable"], "Property Address", "addr"),
      { ...s("seller.address.display", "display"), section: "Seller Address" },
      s("seller.address.components", "components"),
      s("seller.address.city", "city"),
      s("seller.address.province", "province"),
      s("seller.address.postal", "postal"),
      s("seller.address.geocode_string", "geocode_string"),
      { ...s("buyer.address.display", "display"), section: "Buyer Address" },
      s("buyer.address.components", "components"),
      s("buyer.address.city", "city"),
      s("buyer.address.province", "province"),
      s("buyer.address.postal", "postal"),
      s("buyer.address.geocode_string", "geocode_string"),
      { ...s("pin.original", "original"), section: "PIN" },
      s("pin.display", "display"),
      s("pin.api_format", "api_format"),
      { ...s("arn.original", "original"), section: "ARN" },
      s("arn.display", "display"),
      s("arn.api_format", "api_format"),
    ];
    case "parcel_links": return [
      { ...s("resolved_arn"), section: "Parcel" },
      s("method"),
      s("parcel_file"),
      s("reason"),
    ];
    case "clean": return [
      { ...s("transaction.sale_date"), section: "Transaction" },
      s("transaction.sale_price"),
      s("transaction.city"),
      s("transaction.region"),
      s("transaction.transaction_note"),
      ...expandArray("property.addresses", ["display", "components", "geocode_string", "geocodable"], "Property", "addr"),
      s("property.city"),
      s("property.region"),
      s("property.postal"),
      { ...s("seller.parties"), section: "Seller" },
      s("seller.contacts"),
      s("seller.phone"),
      s("seller.trade_name"),
      s("seller.address.display", "addr display"),
      s("seller.address.components", "addr components"),
      s("seller.address.city", "addr city"),
      s("seller.address.province", "addr province"),
      s("seller.address.postal", "addr postal"),
      s("seller.address.country", "addr country"),
      s("seller.address.geocode_string", "geocode_string"),
      { ...s("buyer.parties"), section: "Buyer" },
      s("buyer.contacts"),
      s("buyer.phone"),
      s("buyer.trade_name"),
      s("buyer.address.display", "addr display"),
      s("buyer.address.components", "addr components"),
      s("buyer.address.city", "addr city"),
      s("buyer.address.province", "addr province"),
      s("buyer.address.postal", "addr postal"),
      s("buyer.address.country", "addr country"),
      s("buyer.address.geocode_string", "geocode_string"),
      { ...s("site.pin.original", "pin original"), section: "Site" },
      s("site.pin.display", "pin display"),
      s("site.pin.api_format", "pin api_format"),
      s("site.arn.original", "arn original"),
      s("site.arn.display", "arn display"),
      s("site.arn.api_format", "arn api_format"),
      s("site.acreage"),
      s("site.legal_description"),
      { ...s("parcel.resolved_arn"), section: "Parcel" },
      s("parcel.method"),
      s("parcel.parcel_file"),
      { ...s("consideration.cash"), section: "Financial" },
      s("consideration.debt"),
      s("consideration.charges"),
      s("broker.brokers"),
      { ...s("photos.street_photo_urls"), section: "Media" },
      s("photos.aerial_photo_urls"),
      { ...s("description.description"), section: "Other" },
    ];
    default: return [];
  }
}

// ============================================================
// Helpers
// ============================================================

function getNestedValue(obj: any, path: string): any {
  if (!path || !obj) return undefined;
  return path.split(".").reduce((acc, key) => {
    if (acc == null) return undefined;
    // Handle array index notation like "addresses[0]"
    const arrMatch = key.match(/^(.+)\[(\d+)\]$/);
    if (arrMatch) {
      const arr = acc[arrMatch[1]];
      return Array.isArray(arr) ? arr[parseInt(arrMatch[2])] : undefined;
    }
    return acc[key];
  }, obj);
}

function getStageRecord(trace: TraceData, stage: string): any | null {
  const d = trace.stages[stage];
  if (!d) return null;
  if (Array.isArray(d)) return d[0]?.data ?? null;
  return d?.data ?? null;
}


function valueStatus(val: any): "present" | "missing" | "empty" | "null" {
  if (val === undefined) return "missing";
  if (val === null) return "null";
  if (val === "") return "empty";
  if (Array.isArray(val) && val.length === 0) return "empty";
  return "present";
}


// Format value showing actual content, not just counts
function formatValueFull(val: any): string {
  if (val === undefined) return "";
  if (val === null) return "null";
  if (val === "") return '""';
  if (typeof val === "string") return val;
  if (typeof val === "number") return val.toLocaleString();
  if (typeof val === "boolean") return String(val);
  if (Array.isArray(val)) {
    if (val.length === 0) return "[]";
    return val.map((v) => {
      if (typeof v === "string") return v;
      if (typeof v === "object" && v !== null) return JSON.stringify(v, null, 1);
      return String(v);
    }).join("\n");
  }
  if (typeof val === "object") {
    return Object.entries(val).map(([k, v]) => {
      if (v === null) return `${k}: null`;
      if (typeof v === "string") return `${k}: ${v}`;
      if (typeof v === "number" || typeof v === "boolean") return `${k}: ${v}`;
      if (Array.isArray(v)) return `${k}: [${v.map((x) => typeof x === "string" ? x : JSON.stringify(x)).join(", ")}]`;
      if (typeof v === "object") return `${k}: ${JSON.stringify(v)}`;
      return `${k}: ${v}`;
    }).join("\n");
  }
  return String(val);
}

// ============================================================
// FieldRow component
// ============================================================

function FieldRow({ field, value, connectedSet, lockedField, onHover, onClick }: {
  field: FieldDef;
  value: any;
  connectedSet: Set<string> | null;
  lockedField: string | null;
  onHover: (id: string | null) => void;
  onClick: (id: string, value: any) => void;
}) {
  const status = valueStatus(value);
  const inChain = connectedSet ? connectedSet.has(field.id) : false;
  const dimmed = connectedSet && !inChain;
  const isLocked = lockedField === field.id;

  const bg = isLocked ? "var(--jade-3)"
    : (inChain && connectedSet) ? "var(--jade-2)"
    : status === "missing" ? "var(--red-2)"
    : status === "empty" ? "var(--amber-2)"
    : status === "null" ? "var(--gray-2)"
    : "white";

  return (
    <div
      data-field-id={field.id}
      className="flex items-start gap-1 px-2 py-1 text-[12px] border-b cursor-pointer transition-opacity"
      style={{
        borderColor: isLocked ? "var(--jade-6)" : "var(--gray-3)",
        background: bg,
        opacity: dimmed ? 0.15 : 1,
      }}
      onMouseEnter={() => { if (!lockedField) onHover(field.id); }}
      onMouseLeave={() => { if (!lockedField) onHover(null); }}
      onClick={() => onClick(field.id, value)}
    >
      {/* Incoming connector dot */}
      <div className="connector-in w-2 h-2 rounded-full flex-shrink-0 mt-1" style={{
        background: inChain ? "var(--jade-9)" : "var(--gray-5)",
        border: "1px solid white",
      }} />

      {/* Field name */}
      <span className="font-mono flex-shrink-0 mt-px" style={{ color: "var(--gray-11)", minWidth: 80 }}>
        {field.label}
      </span>

      {/* Value — show full content */}
      <span className="flex-1 font-mono break-words" style={{
        color: status === "missing" ? "var(--red-9)"
          : status === "empty" ? "var(--amber-9)"
          : status === "null" ? "var(--gray-8)"
          : "var(--gray-12)",
        fontStyle: status !== "present" ? "italic" : "normal",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}>
        {status === "missing" ? "MISSING" : status === "empty" ? "EMPTY" : formatValueFull(value)}
      </span>

      {/* Outgoing connector dot */}
      <div className="connector-out w-2 h-2 rounded-full flex-shrink-0 mt-1" style={{
        background: inChain ? "var(--jade-9)" : "var(--gray-5)",
        border: "1px solid white",
      }} />
    </div>
  );
}

// ============================================================
// StageNode component
// ============================================================

function StageNode({ label, fields, data, connectedSet, lockedField, onHover, onFieldClick }: {
  label: string;
  fields: FieldDef[];
  data: any;
  connectedSet: Set<string> | null;
  lockedField: string | null;
  onHover: (id: string | null) => void;
  onFieldClick: (id: string, value: any) => void;
}) {
  let lastSection = "";
  return (
    <div className="rounded-lg border overflow-hidden" style={{
      borderColor: "var(--gray-6)",
      background: "white",
      width: 260,
      flexShrink: 0,
    }}>
      <div className="px-3 py-2 border-b" style={{ borderColor: "var(--gray-4)", background: "var(--gray-2)" }}>
        <Text size="2" weight="medium">{label}</Text>
      </div>
      <div>
        {fields.map((f) => {
          const showSection = f.section && f.section !== lastSection;
          if (f.section) lastSection = f.section;
          const value = getNestedValue(data, f.path);
          return (
            <div key={f.id}>
              {showSection && (
                <div className="px-2 py-0.5 text-[10px] font-medium" style={{ color: "var(--gray-8)", background: "var(--gray-1)" }}>
                  {f.section}
                </div>
              )}
              <FieldRow field={f} value={value} connectedSet={connectedSet} lockedField={lockedField} onHover={onHover} onClick={onFieldClick} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// Main component
// ============================================================

const STAGE_ORDER = [
  { key: "assembled", label: "Assembled" },
  { key: "classified", label: "Classified" },
  { key: "addresses", label: "Addresses" },
  { key: "parcel_links", label: "Parcel Links" },
  { key: "clean", label: "Clean Record" },
];

export default function PipelineFlowView({ trace, rawHtml }: { trace: TraceData; rawHtml: string | null }) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [svgPaths, setSvgPaths] = useState<PathData[]>([]);
  const [hoveredField, setHoveredField] = useState<string | null>(null);
  const [lockedField, setLockedField] = useState<string | null>(null);
  const [selectedValue, setSelectedValue] = useState<{ id: string; value: any } | null>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });

  // Merge static + dynamic connections based on actual data
  const allConnections = useMemo(() => [
    ...CONNECTIONS,
    ...buildDynamicConnections(trace),
  ], [trace]);

  const activeField = lockedField || hoveredField;
  const connectedSet = useMemo(() => {
    if (!activeField) return null;
    // Build chain using all connections (static + dynamic)
    const chain = new Set<string>([activeField]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const c of allConnections) {
        if (chain.has(c.from) && !chain.has(c.to)) { chain.add(c.to); changed = true; }
        if (chain.has(c.to) && !chain.has(c.from)) { chain.add(c.from); changed = true; }
      }
    }
    return chain;
  }, [activeField, allConnections]);

  const handleFieldClick = useCallback((id: string, value: any) => {
    if (lockedField === id) {
      // Clicking the locked field unlocks it
      setLockedField(null);
      setSelectedValue(null);
    } else {
      // Lock to this field
      setLockedField(id);
      setSelectedValue({ id, value });
    }
  }, [lockedField]);

  // Measure and draw SVG paths — uses the inner content div as coordinate origin
  const innerRef = useRef<HTMLDivElement>(null);

  const measurePaths = useCallback(() => {
    const inner = innerRef.current;
    if (!inner) return;

    const paths: PathData[] = [];
    const innerRect = inner.getBoundingClientRect();

    setCanvasSize({ width: inner.scrollWidth, height: inner.scrollHeight });

    for (const conn of allConnections) {
      const fromEl = inner.querySelector(`[data-field-id="${conn.from}"] .connector-out`);
      const toEl = inner.querySelector(`[data-field-id="${conn.to}"] .connector-in`);
      if (!fromEl || !toEl) continue;

      const fromRect = fromEl.getBoundingClientRect();
      const toRect = toEl.getBoundingClientRect();

      const x1 = fromRect.left + fromRect.width / 2 - innerRect.left;
      const y1 = fromRect.top + fromRect.height / 2 - innerRect.top;
      const x2 = toRect.left + toRect.width / 2 - innerRect.left;
      const y2 = toRect.top + toRect.height / 2 - innerRect.top;

      const dx = (x2 - x1) * 0.4;
      const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

      paths.push({ d, color: TYPE_COLORS[conn.type] || TYPE_COLORS.pass, from: conn.from, to: conn.to, type: conn.type });
    }
    setSvgPaths(paths);
  }, [allConnections]);

  // Measure after render + re-measure on resize
  useLayoutEffect(() => {
    // Wait two frames for layout to fully settle (fonts, flex, etc.)
    let frame1: number, frame2: number;
    frame1 = requestAnimationFrame(() => {
      frame2 = requestAnimationFrame(() => {
        measurePaths();
      });
    });
    return () => { cancelAnimationFrame(frame1); cancelAnimationFrame(frame2); };
  }, [trace, measurePaths]);

  return (
    <div className="flex flex-col">
      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-2 border-b flex-wrap" style={{ borderColor: "var(--gray-4)", background: "var(--gray-1)" }}>
        <span className="text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Line types:</span>
        {Object.entries(TYPE_LABELS).map(([type, label]) => (
          <span key={type} className="flex items-center gap-1 text-[11px]">
            <span className="inline-block w-4 h-0.5 rounded" style={{ background: TYPE_COLORS[type] }} />
            <span style={{ color: "var(--gray-9)" }}>{label}</span>
          </span>
        ))}
        <span className="ml-2 text-[11px]" style={{ color: "var(--gray-8)" }}>|</span>
        <span className="flex items-center gap-1 text-[11px]">
          <span className="inline-block w-3 h-3 rounded" style={{ background: "var(--red-2)", border: "1px solid var(--red-4)" }} />
          <span style={{ color: "var(--gray-9)" }}>Missing</span>
        </span>
        <span className="flex items-center gap-1 text-[11px]">
          <span className="inline-block w-3 h-3 rounded" style={{ background: "var(--amber-2)", border: "1px solid var(--amber-4)" }} />
          <span style={{ color: "var(--gray-9)" }}>Empty</span>
        </span>
      </div>

      {/* Canvas */}
      <div ref={canvasRef} className="overflow-x-auto overflow-y-auto" style={{ maxHeight: "calc(100vh - 280px)" }}>
        {/* Inner content div — SVG and nodes share this coordinate space */}
        <div ref={innerRef} className="relative flex p-6" style={{ minWidth: "fit-content", gap: 140 }}>
          {/* SVG overlay — positioned inside inner so it scrolls with content */}
          <svg
            className="absolute top-0 left-0 pointer-events-none"
            style={{ width: canvasSize.width || "100%", height: canvasSize.height || "100%", zIndex: 10 }}
          >
            {svgPaths.map((p, i) => {
              const isHighlighted = connectedSet && connectedSet.has(p.from) && connectedSet.has(p.to);
              const isDimmed = connectedSet && !isHighlighted;
              return (
                <path
                  key={i}
                  d={p.d}
                  fill="none"
                  stroke={p.color}
                  strokeWidth={isHighlighted ? 2.5 : 1.2}
                  strokeOpacity={isDimmed ? 0.08 : isHighlighted ? 1 : 0.35}
                  strokeDasharray={p.type === "pass" ? "4 3" : "none"}
                />
              );
            })}
          </svg>
          {/* Raw HTML iframe */}
          <div className="rounded-lg border flex-shrink-0 flex flex-col" style={{ borderColor: "var(--gray-6)", width: 600 }}>
            <div className="px-3 py-2 border-b" style={{ borderColor: "var(--gray-4)", background: "var(--gray-2)" }}>
              <Text size="2" weight="medium">Raw Source HTML</Text>
            </div>
            {rawHtml ? (
              <iframe
                srcDoc={rawHtml}
                className="w-full border-0 flex-1"
                style={{ minHeight: 600 }}
                sandbox=""
                title="Raw HTML source"
              />
            ) : (
              <div className="flex items-center justify-center" style={{ height: 200 }}>
                <Text size="2" style={{ color: "var(--gray-8)" }}>No raw HTML available</Text>
              </div>
            )}
          </div>

          {/* Stage nodes */}
          {STAGE_ORDER.map((s) => (
            <StageNode
              key={s.key}
              label={s.label}
              fields={stageFields(s.key, getStageRecord(trace, s.key))}
              data={getStageRecord(trace, s.key)}
              connectedSet={connectedSet}
              lockedField={lockedField}
              onHover={setHoveredField}
              onFieldClick={handleFieldClick}
            />
          ))}
        </div>
      </div>

      {/* Selected value detail */}
      {selectedValue && (
        <div className="border-t px-4 py-3" style={{ borderColor: "var(--gray-4)", background: "var(--gray-1)" }}>
          <div className="flex items-center justify-between mb-2">
            <Text size="2" weight="medium" className="font-mono">{selectedValue.id}</Text>
            <button className="text-[12px] px-2 py-0.5 rounded" style={{ color: "var(--gray-9)" }}
              onClick={() => setSelectedValue(null)}>Close</button>
          </div>
          <pre className="text-[12px] font-mono p-3 rounded overflow-auto" style={{
            background: "white", border: "1px solid var(--gray-4)", maxHeight: 200,
            color: "var(--gray-12)", whiteSpace: "pre-wrap",
          }}>
            {JSON.stringify(selectedValue.value, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
