import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import { formatDate } from "../lib/utils";
import type { BrandTokenDetail, ExplorerPartySide } from "../types";

export default function ExplorerBrandDetail() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<BrandTokenDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetchApi<BrandTokenDetail>(`/explorer/brands/${encodeURIComponent(token)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [token]);

  if (err) return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  if (!data) return <div className="p-6"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text></div>;

  const addr = (p: ExplorerPartySide) =>
    [p.street_number, p.street_name, p.street_suffix].filter(Boolean).join(" ") || "—";

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <Link to="/explorer/brands" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Explorer
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-1">
        <Heading size="6" className="font-mono">{data.token}</Heading>
        {data.is_distinctive ? <Badge color="jade">distinctive</Badge>
                              : <Badge variant="soft" color="gray">common</Badge>}
        {data.is_excluded ? <Badge color="red">excluded</Badge> : null}
      </div>

      <div className="grid grid-cols-4 gap-4 mt-5">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>IDF</Text>
          <Heading size="5" mt="2">{data.idf.toFixed(2)}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Party-sides</Text>
          <Heading size="5" mt="2">{data.n_party_sides.toLocaleString()}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Distinct phrases</Text>
          <Heading size="5" mt="2">{data.n_distinct_phrases.toLocaleString()}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Phrase / party ratio</Text>
          <Heading size="5" mt="2">
            {(data.n_distinct_phrases / Math.max(1, data.n_party_sides)).toFixed(2)}
          </Heading>
        </div>
      </div>

      <Heading size="4" mt="6" mb="2">Brand phrases containing this token</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
        <div className="flex flex-wrap gap-1">
          {data.phrases.map((p) => (
            <Badge key={p} size="2" variant="soft" color="gray">{p}</Badge>
          ))}
        </div>
      </div>

      <Heading size="4" mt="6" mb="2">
        Party-sides ({data.party_sides.length.toLocaleString()})
      </Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">source_id</th>
              <th className="text-left p-2 font-medium">side</th>
              <th className="text-left p-2 font-medium">sale_date</th>
              <th className="text-left p-2 font-medium">address</th>
              <th className="text-left p-2 font-medium">postal</th>
              <th className="text-left p-2 font-medium">phone</th>
              <th className="text-left p-2 font-medium">contact</th>
            </tr>
          </thead>
          <tbody>
            {data.party_sides.map((p) => (
              <tr key={`${p.source_id}-${p.side}`} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">{p.source_id}</td>
                <td className="p-2">{p.side}</td>
                <td className="p-2">{p.sale_date ? formatDate(p.sale_date) : "—"}</td>
                <td className="p-2">{addr(p)}</td>
                <td className="p-2">{p.postal || "—"}</td>
                <td className="p-2">{p.phone || "—"}</td>
                <td className="p-2">{p.contact_fingerprint || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
