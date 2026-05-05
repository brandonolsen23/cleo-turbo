import { useEffect, useState, useMemo } from "react";
import { Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import PropertyMiniMap from "../ui/PropertyMiniMap";
import type { TenuredFootprintResponse, MiniMapProperty } from "../../types";

const TENURE_COLORS = ["var(--jade-9)", "var(--blue-9)", "var(--purple-9)", "var(--orange-9)"];
const UNATTRIBUTED_COLOR = "var(--gray-7)";

interface Props {
  contactId: string;
  height?: number;
}

export default function TenuredPropertyFootprintMap({ contactId, height = 280 }: Props) {
  const [data, setData] = useState<TenuredFootprintResponse | null>(null);

  useEffect(() => {
    fetchApi<TenuredFootprintResponse>(
      `/contacts/${contactId}/property-footprint-tenured`,
    ).then(setData);
  }, [contactId]);

  // Build a stem → color map from the (sorted) set of stems present.
  const stemColors = useMemo(() => {
    if (!data) return {} as Record<string, string>;
    const stems = Array.from(new Set(
      data.properties.map((p) => p.tenure_stem).filter((s): s is string => !!s),
    )).sort();
    const m: Record<string, string> = {};
    stems.forEach((s, i) => { m[s] = TENURE_COLORS[i % TENURE_COLORS.length]; });
    return m;
  }, [data]);

  if (!data) return null;

  // PropertyMiniMap doesn't accept per-pin colors today. We render a legend
  // here and pass the properties through; the visual color coding is a
  // future PR (or a small extension to PropertyMiniMap to read pin_color
  // from the property objects).
  const props: MiniMapProperty[] = data.properties.map((p) => ({
    id: p.id,
    display_address: p.display_address,
    city: p.city,
    lat: p.lat,
    lng: p.lng,
    asset_class: p.asset_class,
    most_recent_sale_price: p.most_recent_sale_price,
  }));

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <Text size="3" weight="medium" className="mb-3 block">
        Property Footprint ({data.properties.length})
      </Text>
      <PropertyMiniMap properties={props} height={height} />
      {Object.keys(stemColors).length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {Object.entries(stemColors).map(([stem, color]) => (
            <Badge key={stem} size="1" variant="soft" style={{ color }}>
              ● {stem}
            </Badge>
          ))}
          <Badge size="1" variant="soft" style={{ color: UNATTRIBUTED_COLOR }}>
            ● unattributed
          </Badge>
        </div>
      )}
    </div>
  );
}
