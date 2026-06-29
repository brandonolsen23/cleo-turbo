import { Text, Badge, Button } from "@radix-ui/themes";
import { LinkedinLogo, Buildings, MapPin } from "@phosphor-icons/react";
import type { CareerHistoryRow, WorkHistoryPosition } from "../../types";
import { formatDate, titleCase, formatCanonicalAddress } from "../../lib/utils";

interface ReconciledRow {
  // From CareerHistoryRow when matched
  brand_stem: string | null;
  // Display strings
  display_name: string;
  date_range: string;
  duration: string | null;
  // Source pills
  has_linkedin: boolean;
  has_realtrack: boolean;
  // Realtrack metadata (when applicable)
  n_transactions_credited: number;
  is_active: boolean;
  dominant_address_unit: string | null;
  // LinkedIn metadata (when applicable)
  title: string | null;
  // Click target — whichever side has it
  brand_stem_for_click: string | null;
}

function formatYear(d: string | null): string {
  if (!d) return "?";
  return d.slice(0, 4);
}

function formatRange(start: string | null, end: string | null, isCurrent: boolean): string {
  const startStr = formatYear(start);
  const endStr = isCurrent ? "Present" : formatYear(end);
  return `${startStr} – ${endStr}`;
}

function durationStr(start: string | null, end: string | null, isCurrent: boolean): string | null {
  if (!start) return null;
  const sd = new Date(start);
  const ed = isCurrent ? new Date() : end ? new Date(end) : null;
  if (!ed) return null;
  const months = (ed.getFullYear() - sd.getFullYear()) * 12 + (ed.getMonth() - sd.getMonth());
  if (months < 12) return `${months} mo`;
  const years = Math.floor(months / 12);
  const rem = months % 12;
  return rem > 0 ? `${years} yr ${rem} mo` : `${years} yr`;
}

function reconcile(
  realtrack: CareerHistoryRow[],
  linkedIn: WorkHistoryPosition[],
): ReconciledRow[] {
  const out: ReconciledRow[] = [];
  const usedRtStems = new Set<string>();

  // 1) For each LinkedIn position, try to find a matching realtrack tenure by
  //    substring containment of stem in lowercased company.
  for (const li of linkedIn) {
    const liCompanyLower = (li.company || "").toLowerCase();
    const matchRt = realtrack.find(
      (rt) => !usedRtStems.has(rt.brand_stem) && liCompanyLower.includes(rt.brand_stem),
    );
    if (matchRt) usedRtStems.add(matchRt.brand_stem);
    out.push({
      brand_stem: matchRt?.brand_stem ?? null,
      display_name: li.company || matchRt?.display_name || "—",
      date_range: formatRange(li.start_date, li.end_date, li.is_current),
      duration: durationStr(li.start_date, li.end_date, li.is_current),
      has_linkedin: true,
      has_realtrack: !!matchRt,
      n_transactions_credited: matchRt?.n_transactions_credited ?? 0,
      is_active: li.is_current || matchRt?.is_active === 1,
      dominant_address_unit: matchRt?.dominant_address_unit ?? null,
      title: li.title,
      brand_stem_for_click: matchRt?.brand_stem ?? null,
    });
  }

  // 2) Realtrack tenures with no matching LinkedIn position — append.
  for (const rt of realtrack) {
    if (usedRtStems.has(rt.brand_stem)) continue;
    out.push({
      brand_stem: rt.brand_stem,
      display_name: rt.display_name,
      date_range: formatRange(rt.inferred_start_date, rt.inferred_end_date, rt.is_active === 1),
      duration: durationStr(rt.inferred_start_date, rt.inferred_end_date, rt.is_active === 1),
      has_linkedin: false,
      has_realtrack: true,
      n_transactions_credited: rt.n_transactions_credited,
      is_active: rt.is_active === 1,
      dominant_address_unit: rt.dominant_address_unit,
      title: null,
      brand_stem_for_click: rt.brand_stem,
    });
  }

  return out;
}

interface Props {
  realtrack: CareerHistoryRow[];
  linkedIn: WorkHistoryPosition[];
  totalSpvCount?: number;
  onRowClick: (stem: string) => void;
  onViewSpvs?: () => void;
}

export default function CareerHistoryTile({
  realtrack, linkedIn, totalSpvCount, onRowClick, onViewSpvs,
}: Props) {
  const rows = reconcile(realtrack, linkedIn);

  if (rows.length === 0) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Text size="3" weight="medium" className="mb-2 block">Career History</Text>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          No career history yet. Add a LinkedIn profile or wait for the next
          discovery rebuild.
        </Text>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-center justify-between mb-3">
        <Text size="3" weight="medium">Career History ({rows.length})</Text>
      </div>
      <div className="flex flex-col gap-4">
        {rows.map((r, i) => (
          <button
            key={`${r.brand_stem ?? r.display_name}-${i}`}
            onClick={() => r.brand_stem_for_click && onRowClick(r.brand_stem_for_click)}
            disabled={!r.brand_stem_for_click}
            className="text-left flex flex-col gap-1 hover:bg-[var(--gray-a2)] rounded p-2 -m-2 disabled:cursor-default disabled:hover:bg-transparent"
          >
            <div className="flex items-center gap-2">
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{
                  backgroundColor: r.is_active ? "var(--jade-9)" : "var(--gray-7)",
                }}
              />
              <Text size="2" weight="medium">
                {r.title ? `${titleCase(r.title)} · ` : ""}{titleCase(r.display_name)}
              </Text>
              {r.is_active && (
                <Badge size="1" color="jade" variant="soft">Current</Badge>
              )}
            </div>
            <Text size="1" style={{ color: "var(--gray-9)" }}>
              {r.date_range}{r.duration ? ` · ${r.duration}` : ""}
            </Text>
            <div className="flex flex-wrap gap-1 mt-1">
              {r.has_linkedin && (
                <Badge size="1" color="jade" variant="soft">
                  <LinkedinLogo size={10} weight="fill" /> via LinkedIn
                </Badge>
              )}
              {r.has_realtrack && (
                <Badge size="1" color="gray" variant="soft">
                  <Buildings size={10} /> via Realtrack · {r.n_transactions_credited} transactions credited
                </Badge>
              )}
            </div>
            {r.dominant_address_unit && (
              <div className="flex items-center gap-1 mt-0.5">
                <MapPin size={11} style={{ color: "var(--gray-8)" }} />
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  {formatCanonicalAddress(r.dominant_address_unit)} · primary address during this tenure
                </Text>
              </div>
            )}
          </button>
        ))}
      </div>
      {totalSpvCount !== undefined && totalSpvCount > 0 && (
        <button
          onClick={onViewSpvs}
          className="mt-3 text-[13px] no-underline"
          style={{ color: "var(--accent-11)" }}
        >
          View {totalSpvCount} SPVs credited to these tenures →
        </button>
      )}
    </div>
  );
}
