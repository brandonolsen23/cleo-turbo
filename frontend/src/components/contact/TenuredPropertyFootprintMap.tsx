import { useEffect, useState, useMemo } from "react";
import { Text } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import PropertyMiniMap from "../ui/PropertyMiniMap";
import { titleCase } from "../../lib/utils";
import type { TenuredFootprintResponse, MiniMapProperty } from "../../types";

const TENURE_COLORS = ["var(--jade-9)", "var(--blue-9)", "var(--purple-9)", "var(--orange-9)"];
const UNATTRIBUTED_COLOR = "var(--gray-7)";
const UNATTRIBUTED_KEY = "__unattributed__";

interface Props {
  contactId: string;
  height?: number;
}

export default function TenuredPropertyFootprintMap({ contactId, height = 280 }: Props) {
  const [data, setData] = useState<TenuredFootprintResponse | null>(null);
  const [selected, setSelected] = useState<Set<string> | null>(null);

  useEffect(() => {
    fetchApi<TenuredFootprintResponse>(
      `/contacts/${contactId}/property-footprint-tenured`,
    ).then(setData);
  }, [contactId]);

  // stem → color map (sorted, with unattributed pinned to the end).
  const stemColors = useMemo(() => {
    if (!data) return {} as Record<string, string>;
    const stems = Array.from(new Set(
      data.properties.map((p) => p.tenure_stem).filter((s): s is string => !!s),
    )).sort();
    const m: Record<string, string> = {};
    stems.forEach((s, i) => { m[s] = TENURE_COLORS[i % TENURE_COLORS.length]; });
    return m;
  }, [data]);

  // Has any unattributed properties?
  const hasUnattributed = useMemo(
    () => !!data?.properties.some((p) => !p.tenure_stem),
    [data],
  );

  // Initialize selected to all-keys-active on first data load
  useEffect(() => {
    if (!data || selected !== null) return;
    const all = new Set(Object.keys(stemColors));
    if (hasUnattributed) all.add(UNATTRIBUTED_KEY);
    setSelected(all);
  }, [data, stemColors, hasUnattributed, selected]);

  if (!data || !selected) return null;

  // Filter properties by which stems are currently selected
  const filtered = data.properties.filter((p) => {
    if (!p.tenure_stem) return selected.has(UNATTRIBUTED_KEY);
    return selected.has(p.tenure_stem);
  });

  const props: MiniMapProperty[] = filtered.map((p) => ({
    id: p.id,
    display_address: p.display_address,
    city: p.city,
    lat: p.lat,
    lng: p.lng,
    asset_class: p.asset_class,
    most_recent_sale_price: p.most_recent_sale_price,
  }));

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const renderTag = (key: string, label: string, color: string) => {
    const active = selected.has(key);
    return (
      <button
        key={key}
        type="button"
        onClick={() => toggle(key)}
        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] transition-opacity"
        style={{
          backgroundColor: active ? "var(--gray-3)" : "transparent",
          border: `1px solid ${active ? "var(--gray-6)" : "var(--gray-5)"}`,
          opacity: active ? 1 : 0.45,
          color: "var(--gray-12)",
          cursor: "pointer",
        }}
        aria-pressed={active}
      >
        <span style={{ color, fontSize: 9 }}>●</span>
        <span style={{ fontWeight: active ? 500 : 400 }}>{label}</span>
      </button>
    );
  };

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <Text size="3" weight="medium">
          Property Footprint ({filtered.length}
          {filtered.length !== data.properties.length && ` of ${data.properties.length}`})
        </Text>
      </div>
      <PropertyMiniMap properties={props} height={height} />
      {(Object.keys(stemColors).length > 0 || hasUnattributed) && (
        <div className="flex flex-wrap gap-2 mt-3">
          {Object.entries(stemColors).map(([stem, color]) =>
            renderTag(stem, titleCase(stem), color),
          )}
          {hasUnattributed &&
            renderTag(UNATTRIBUTED_KEY, "Unattributed", UNATTRIBUTED_COLOR)}
        </div>
      )}
    </div>
  );
}
