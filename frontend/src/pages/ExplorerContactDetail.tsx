import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { ContactFingerprintDetail } from "../types";
import PartySideCard from "../components/explorer/PartySideCard";
import SiloTimeline from "../components/explorer/SiloTimeline";

function titleCase(s: string): string {
  return s.split(" ").map(w => w ? w[0].toUpperCase() + w.slice(1) : w).join(" ");
}

export default function ExplorerContactDetail() {
  const { fingerprint } = useParams<{ fingerprint: string }>();
  const [data, setData] = useState<ContactFingerprintDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!fingerprint) return;
    fetchApi<ContactFingerprintDetail>(`/explorer/contacts/${encodeURIComponent(fingerprint)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [fingerprint]);

  if (err) return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  if (!data) return <div className="p-6"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text></div>;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <Link to="/explorer/contacts" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Contacts
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-1 flex-wrap">
        <Heading size="6">{titleCase(data.contact_fingerprint)}</Heading>
        <Text size="3" className="font-mono" style={{ color: "var(--gray-9)" }}>
          {data.contact_fingerprint}
        </Text>
      </div>

      <div className="grid grid-cols-1 gap-4 mt-5 max-w-sm">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Party-sides</Text>
          <Heading size="5" mt="2">{data.n_party_sides.toLocaleString()}</Heading>
        </div>
      </div>

      <SiloTimeline anchorType="contact" value={fingerprint!} />

      <Heading size="4" mt="6" mb="2">
        Party-sides ({data.party_sides.length.toLocaleString()})
      </Heading>
      <div className="flex flex-col gap-3">
        {data.party_sides.map((p) => (
          <PartySideCard key={`${p.source_id}-${p.side}`} partySide={p} />
        ))}
      </div>
    </div>
  );
}
