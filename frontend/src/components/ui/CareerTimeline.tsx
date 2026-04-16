import { Text, Badge } from "@radix-ui/themes";
import { Briefcase } from "@phosphor-icons/react";
import type { WorkHistoryPosition } from "../../types";

function formatDateRange(start: string | null, end: string | null, isCurrent: boolean): string {
  const fmt = (d: string | null) => {
    if (!d) return "?";
    // Handle YYYY-MM or YYYY format
    if (d.length === 7) {
      const [y, m] = d.split("-");
      const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      return `${months[parseInt(m, 10) - 1]} ${y}`;
    }
    return d; // Just year
  };
  const startStr = fmt(start);
  const endStr = isCurrent ? "Present" : fmt(end);
  return `${startStr} \u2013 ${endStr}`;
}

function computeDuration(start: string | null, end: string | null, isCurrent: boolean): string | null {
  if (!start) return null;
  const startDate = new Date(start.length === 4 ? `${start}-01` : start);
  const endDate = isCurrent ? new Date() : (end ? new Date(end.length === 4 ? `${end}-01` : end) : null);
  if (!endDate) return null;
  const months = (endDate.getFullYear() - startDate.getFullYear()) * 12 + (endDate.getMonth() - startDate.getMonth());
  if (months < 12) return `${months} mo`;
  const years = Math.floor(months / 12);
  const rem = months % 12;
  return rem > 0 ? `${years} yr ${rem} mo` : `${years} yr`;
}

/**
 * Full career timeline for the ContactDetailPage.
 */
export default function CareerTimeline({ positions }: { positions: WorkHistoryPosition[] }) {
  if (!positions || positions.length === 0) return null;

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-center gap-2 mb-3">
        <Briefcase size={16} style={{ color: "var(--gray-9)" }} />
        <Text size="3" weight="medium">Career History</Text>
        <Badge size="1" variant="soft" color="jade">{positions.length} position{positions.length !== 1 ? "s" : ""}</Badge>
      </div>

      <div className="relative ml-2">
        {/* Vertical line */}
        <div
          className="absolute left-[5px] top-2 bottom-2 w-px"
          style={{ backgroundColor: "var(--gray-5)" }}
        />

        {positions.map((pos, i) => (
          <div key={pos.id} className="relative flex gap-3 pb-4 last:pb-0">
            {/* Dot */}
            <div
              className="flex-shrink-0 w-[11px] h-[11px] rounded-full mt-1 border-2"
              style={{
                backgroundColor: pos.is_current ? "var(--jade-9)" : "var(--gray-1)",
                borderColor: pos.is_current ? "var(--jade-9)" : "var(--gray-7)",
              }}
            />

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <Text size="2" weight="medium">{pos.title || "Unknown Title"}</Text>
                {!!pos.is_current && <Badge size="1" color="jade" variant="soft">Current</Badge>}
              </div>
              <div className="flex items-center gap-1.5">
                {pos.company_logo_url && (
                  <img
                    src={pos.company_logo_url}
                    alt=""
                    className="w-4 h-4 rounded-sm object-contain"
                    referrerPolicy="no-referrer"
                  />
                )}
                <Text size="2" style={{ color: "var(--gray-11)" }}>
                  {pos.company}
                </Text>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  {formatDateRange(pos.start_date, pos.end_date, !!pos.is_current)}
                </Text>
                {(() => {
                  const dur = computeDuration(pos.start_date, pos.end_date, !!pos.is_current);
                  return dur ? (
                    <Text size="1" style={{ color: "var(--gray-8)" }}>{dur}</Text>
                  ) : null;
                })()}
              </div>
              {pos.location && (
                <Text size="1" style={{ color: "var(--gray-8)" }}>{pos.location}</Text>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Compact inline variant for merge surfaces: shows current position as one line.
 * Use in SuggestedLinksCard, CompareGroupPage, etc.
 */
export function CurrentPositionBadge({
  positions,
  headline,
}: {
  positions?: WorkHistoryPosition[];
  headline?: string | null;
}) {
  // Try to get current position from work history
  const current = positions?.find((p) => p.is_current);

  if (current) {
    return (
      <span className="text-[11px]" style={{ color: "var(--gray-9)" }}>
        {current.title ? `${current.title} at ` : ""}{current.company}
      </span>
    );
  }

  // Fallback to headline
  if (headline) {
    return (
      <span className="text-[11px]" style={{ color: "var(--gray-9)" }}>
        {headline}
      </span>
    );
  }

  return null;
}
