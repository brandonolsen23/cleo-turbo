import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupTrailResponse } from "../../types";
import AutoGroupTrail from "./AutoGroupTrail";


export default function AutoGroupTrailTab() {
  const [searchParams] = useSearchParams();
  const sourceId = searchParams.get("source_id");
  const side = searchParams.get("side");
  const [trail, setTrail] = useState<AutoGroupTrailResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!sourceId || !side) {
      setTrail(null);
      setErr(null);
      return;
    }
    setErr(null);
    fetchApi<AutoGroupTrailResponse>(
      `/explorer/auto-groups/parties/${encodeURIComponent(sourceId)}/${encodeURIComponent(side)}/trail`,
    ).then(setTrail).catch((e) => setErr(String(e)));
  }, [sourceId, side]);

  if (!sourceId || !side) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-8"
           style={{ background: "var(--gray-2)" }}>
        <Heading size="3">Evidence trail</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Pick a party from the Parties tab to see its evidence trail. Click the
          <span className="font-mono">  Trail  </span>
          link on a party row.
        </Text>
      </div>
    );
  }

  if (err) {
    return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  }

  if (!trail) {
    return (
      <div className="p-6">
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading trail…</Text>
      </div>
    );
  }

  return <AutoGroupTrail trail={trail} />;
}
