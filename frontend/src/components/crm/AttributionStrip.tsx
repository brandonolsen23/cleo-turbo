import { useEffect, useState } from "react";
import { Text } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import { formatDate } from "../../lib/utils";
import type { AttributionResponse, CrmEntityType } from "../../types";

interface AttributionStripProps {
  entityType: CrmEntityType;
  entityId: string;
  /** If true, render nothing when there are no activities. Useful when the
   * parent page already shows a "Never contacted" indicator elsewhere. */
  hideWhenEmpty?: boolean;
}

const ENDPOINT_BY_TYPE: Record<CrmEntityType, string> = {
  contact: "/contacts",
  property: "/properties",
  group: "/groups",
};

export default function AttributionStrip({ entityType, entityId, hideWhenEmpty = false }: AttributionStripProps) {
  const [data, setData] = useState<AttributionResponse | null>(null);

  useEffect(() => {
    fetchApi<AttributionResponse>(`${ENDPOINT_BY_TYPE[entityType]}/${entityId}/attribution`)
      .then(setData)
      .catch(() => setData(null));
  }, [entityType, entityId]);

  if (!data) return null;

  if (data.total_activities === 0) {
    if (hideWhenEmpty) return null;
    return (
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        Never contacted
      </Text>
    );
  }

  const renderEvent = (label: string, ev: AttributionResponse["first_contacted"]) => {
    if (!ev) return null;
    const outcomeBit = ev.outcome ? ` → ${ev.outcome}` : "";
    return (
      <div className="flex gap-2 text-[13px] items-baseline">
        <Text size="2" style={{ color: "var(--gray-9)", minWidth: 110 }}>
          {label}
        </Text>
        <Text size="2">
          <span style={{ fontWeight: 500 }}>{ev.user_name ?? "Unknown user"}</span>
          {" · "}
          {formatDate(ev.happened_at)}
          {" · "}
          <span style={{ color: "var(--gray-11)" }}>
            {ev.activity_type}
            {outcomeBit}
          </span>
        </Text>
      </div>
    );
  };

  const byUserStr = data.by_user
    .filter((u) => u.user_name)
    .map((u) => `${u.user_name} (${u.count})`)
    .join(" · ");

  return (
    <div className="flex flex-col gap-1">
      {renderEvent("First contacted", data.first_contacted)}
      {renderEvent("Last contacted", data.last_contacted)}
      <Text size="1" style={{ color: "var(--gray-9)" }}>
        {data.total_activities} {data.total_activities === 1 ? "activity" : "activities"}
        {byUserStr ? ` · ${byUserStr}` : ""}
      </Text>
    </div>
  );
}
