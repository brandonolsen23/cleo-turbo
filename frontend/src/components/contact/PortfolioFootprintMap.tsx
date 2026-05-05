import { useEffect, useState } from "react";
import { Text } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import PropertyMiniMap from "../ui/PropertyMiniMap";
import type { PortfolioFootprintResponse, MiniMapProperty } from "../../types";

interface Props {
  stem: string;
  displayName: string;
  height?: number;
}

export default function PortfolioFootprintMap({ stem, displayName, height = 380 }: Props) {
  const [data, setData] = useState<PortfolioFootprintResponse | null>(null);

  useEffect(() => {
    fetchApi<PortfolioFootprintResponse>(
      `/companies/${encodeURIComponent(stem)}/portfolio-footprint`,
    ).then(setData);
  }, [stem]);

  if (!data) return null;
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
        {displayName} Portfolio ({data.n_transactions} transactions)
      </Text>
      <PropertyMiniMap properties={props} height={height} />
    </div>
  );
}
