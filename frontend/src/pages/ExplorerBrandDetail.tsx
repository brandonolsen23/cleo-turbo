import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge, Button } from "@radix-ui/themes";
import { fetchApi, mutateApi } from "../api/client";
import { formatDate } from "../lib/utils";
import type { BrandTokenDetail, ExplorerPartySide } from "../types";

export default function ExplorerBrandDetail() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<BrandTokenDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetchApi<BrandTokenDetail>(`/explorer/brands/${encodeURIComponent(token)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [token]);

  async function togglePlace() {
    if (!data) return;
    await runToggle("place", data.is_place_name === 1);
  }

  async function toggleIndustry() {
    if (!data) return;
    await runToggle("industry-stopword", data.is_industry_stopword === 1);
  }

  async function runToggle(endpoint: "place" | "industry-stopword", currentlyOn: boolean) {
    if (!data) return;
    setBusy(true);
    try {
      const path = `/explorer/brands/${encodeURIComponent(data.token)}/${endpoint}`;
      await mutateApi(path, currentlyOn ? "DELETE" : "POST");
      const fresh = await fetchApi<BrandTokenDetail>(
        `/explorer/brands/${encodeURIComponent(data.token)}`
      );
      setData(fresh);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (err) return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  if (!data) return <div className="p-6"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text></div>;

  const addr = (p: ExplorerPartySide) =>
    [p.street_number, p.street_name, p.street_suffix].filter(Boolean).join(" ") || "—";

  const reasonBadge = data.filter_reason === null
    ? <Badge color="jade">distinctive</Badge>
    : <Badge variant="soft" color={
        data.filter_reason === "excluded" ? "red" :
        data.filter_reason === "industry" ? "amber" :
        data.filter_reason === "place" ? "blue" : "gray"
      }>{data.filter_reason}</Badge>;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <Link to="/explorer/brands" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Explorer
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-1 flex-wrap">
        <Heading size="6" className="font-mono">{data.token}</Heading>
        {reasonBadge}
        <Button size="1" variant="soft"
                color={data.is_industry_stopword ? "tomato" : "amber"}
                disabled={busy}
                onClick={toggleIndustry}>
          {data.is_industry_stopword ? "Unmark industry stopword" : "Mark as industry stopword"}
        </Button>
        <Button size="1" variant="soft"
                color={data.is_place_name ? "tomato" : "blue"}
                disabled={busy}
                onClick={togglePlace}>
          {data.is_place_name ? "Unmark place name" : "Mark as place name"}
        </Button>
      </div>

      <div className="grid grid-cols-5 gap-4 mt-5">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>IDF (corpus)</Text>
          <Heading size="5" mt="2">{data.idf.toFixed(2)}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Zipf (EN + FR)</Text>
          <Heading size="5" mt="2">
            {data.wordfreq_zipf !== null ? data.wordfreq_zipf.toFixed(2) : "—"}
          </Heading>
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
          <Text size="1" style={{ color: "var(--gray-9)" }}>Phrase / party</Text>
          <Heading size="5" mt="2">
            {(data.n_distinct_phrases / Math.max(1, data.n_party_sides)).toFixed(2)}
          </Heading>
        </div>
      </div>

      <Heading size="4" mt="6" mb="2">Signals</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <div className="flex flex-wrap gap-2 items-center">
          {data.is_english_common ? <Badge color="gray">common EN/FR</Badge> : null}
          {data.is_place_name ? <Badge color="blue">place name</Badge> : null}
          {data.is_industry_stopword ? <Badge color="amber">industry stopword</Badge> : null}
          {data.is_excluded ? <Badge color="red">excluded artifact</Badge> : null}
          {!data.is_english_common && !data.is_place_name && !data.is_industry_stopword && !data.is_excluded
            ? <Badge color="jade">no filter applied</Badge> : null}
          <Text size="2" style={{ color: "var(--gray-9)", marginLeft: "auto" }}>
            filter_reason: <strong>{data.filter_reason || "distinctive"}</strong>
          </Text>
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
