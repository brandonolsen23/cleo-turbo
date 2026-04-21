import type {
  FieldType, LabelingLinkInput, LabelingLink, LabelingPartyView, LinkKind,
} from "../../types";

// Frontend-only type. `auto` distinguishes system-proposed links from manually
// drawn ones in the UI; stripped before the POST /verdicts payload.
export type PendingLink = LabelingLinkInput & {
  auto?: "exact" | "learned";
  // Set when an auto-proposed link is considered weak on its own and the
  // user should double-check before confirming. "contact_only" = a
  // contact_name match with no corporate co-signal. "phone_only" = a phone
  // match with no corporate co-signal. Personal signals like these can
  // follow an individual across jobs, so we surface them but don't give
  // them the same confidence as a corroborated match.
  caution?: "contact_only" | "phone_only";
};

interface FieldValue {
  field_type: FieldType;
  value: string;
}

/** Pull every labelable (field_type, value) pair from a party view.
 * Mirrors PartyCard's buildRows — keep the two in sync if either changes. */
function extractValues(view: LabelingPartyView): FieldValue[] {
  const out: FieldValue[] = [];
  for (const p of view.party_rows) {
    if (p.party_name) out.push({ field_type: "party_name", value: p.party_name });
  }
  if (view.trade_name) out.push({ field_type: "trade_name", value: view.trade_name });
  if (view.care_of)    out.push({ field_type: "care_of",    value: view.care_of });
  for (const v of view.companies_other) out.push({ field_type: "company_other", value: v });
  for (const v of view.law_firms)       out.push({ field_type: "law_firm", value: v });
  for (const c of view.contacts) if (c.name)
    out.push({ field_type: "contact_name", value: c.name });
  if (view.mailing?.display) out.push({ field_type: "address", value: view.mailing.display });
  for (const ph of view.phones) out.push({ field_type: "phone", value: ph });
  return out;
}

/** Field types we treat as "corporate" — brand/entity/location evidence
 * that ties a party to a specific organization. A contact_name or phone
 * match is only strong when at least one of these also matches between
 * the same pair, because people (and their direct phone lines) move
 * between jobs while keeping the same name/number. */
const CORPORATE_FIELDS: ReadonlySet<FieldType> = new Set<FieldType>([
  "party_name", "trade_name", "care_of", "company_other", "law_firm", "address",
]);

function isCorporate(ft: FieldType): boolean {
  return CORPORATE_FIELDS.has(ft);
}

/** Post-pass: mark contact_name and phone links as "caution" when no
 * corporate-category link exists in the same proposals list.
 *
 * Operates on the combined (exact + learned) list because corroboration
 * can come from either kind of proposal. Mutates and returns the same
 * array for convenience. */
export function flagUncorroborated(links: PendingLink[]): PendingLink[] {
  const hasCorporate = links.some(
    (l) => isCorporate(l.from_field_type) || isCorporate(l.to_field_type),
  );
  for (const l of links) {
    if (l.from_field_type === "contact_name" || l.to_field_type === "contact_name") {
      if (!hasCorporate) l.caution = "contact_only";
    } else if (l.from_field_type === "phone" || l.to_field_type === "phone") {
      if (!hasCorporate) l.caution = "phone_only";
    }
  }
  return links;
}

/** Exact character-identical matches across any (left field, right field) pair.
 * One Exact link per match. */
export function proposeExactLinks(
  left: LabelingPartyView, right: LabelingPartyView,
): PendingLink[] {
  const leftVals = extractValues(left);
  const rightVals = extractValues(right);
  const out: PendingLink[] = [];
  for (const l of leftVals) {
    for (const r of rightVals) {
      if (l.value === r.value) {
        out.push({
          from_field_type: l.field_type,
          from_field_value: l.value,
          to_field_type: r.field_type,
          to_field_value: r.value,
          kind: "exact",
          auto: "exact",
        });
      }
    }
  }
  return out;
}

/** Build a value → [{ other, kind }] index from confirmed session links.
 * Each link contributes both directions, so a lookup on either side works. */
export function computeLearnedPairs(
  links: LabelingLink[],
): Map<string, { other: string; kind: LinkKind }[]> {
  const map = new Map<string, { other: string; kind: LinkKind }[]>();
  const add = (from: string, to: string, kind: LinkKind) => {
    if (!map.has(from)) map.set(from, []);
    const bucket = map.get(from)!;
    if (!bucket.some((e) => e.other === to && e.kind === kind)) {
      bucket.push({ other: to, kind });
    }
  };
  for (const l of links) {
    add(l.from_field_value, l.to_field_value, l.kind);
    add(l.to_field_value, l.from_field_value, l.kind);
  }
  return map;
}

/** For each left value, if a previously-learned partner appears in the right
 * party, propose the same kind of link. Deduped against proposeExactLinks
 * output — exact wins because it's more informative. */
export function proposeLearnedLinks(
  left: LabelingPartyView,
  right: LabelingPartyView,
  learned: Map<string, { other: string; kind: LinkKind }[]>,
  excludeExact: PendingLink[] = [],
): PendingLink[] {
  const leftVals = extractValues(left);
  const rightVals = extractValues(right);
  const rightIndex = new Map<string, FieldValue[]>();
  for (const r of rightVals) {
    const arr = rightIndex.get(r.value) ?? [];
    arr.push(r);
    rightIndex.set(r.value, arr);
  }

  const out: PendingLink[] = [];
  for (const l of leftVals) {
    const partners = learned.get(l.value);
    if (!partners) continue;
    for (const p of partners) {
      const matches = rightIndex.get(p.other);
      if (!matches) continue;
      for (const m of matches) {
        // Skip if this (from_value, to_value) is already proposed as exact
        const dupOfExact = excludeExact.some(
          (e) => e.from_field_value === l.value && e.to_field_value === m.value,
        );
        if (dupOfExact) continue;
        // Skip if identical (exact would handle it; learned with same string
        // is noise)
        if (l.value === m.value) continue;
        out.push({
          from_field_type: l.field_type,
          from_field_value: l.value,
          to_field_type: m.field_type,
          to_field_value: m.value,
          kind: p.kind,
          auto: "learned",
        });
      }
    }
  }
  return out;
}

/** Strip the `auto` marker before POSTing a verdict. */
export function stripAuto(links: PendingLink[]): LabelingLinkInput[] {
  return links.map(({ auto, ...rest }) => rest);
}
