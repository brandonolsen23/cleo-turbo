import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { BrandTrigramDetail } from "../types";
import PartySideCard from "../components/explorer/PartySideCard";

export default function ExplorerBrandTrigramDetail() {
  const { trigram } = useParams<{ trigram: string }>();
  const [data, setData] = useState<BrandTrigramDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!trigram) return;
    fetchApi<BrandTrigramDetail>(`/explorer/brands/trigrams/${encodeURIComponent(trigram)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [trigram]);

  if (err) return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  if (!data) return <div className="p-6"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text></div>;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <Link to="/explorer/brands/3gram" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Trigrams
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-1 flex-wrap">
        <Heading size="6" className="font-mono">{data.trigram}</Heading>
        <Badge color={data.is_distinctive ? "jade" : "gray"}>
          {data.is_distinctive ? "distinctive" : "not distinctive"}
        </Badge>
      </div>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        tokens: <strong>{data.token_a}</strong> + <strong>{data.token_b}</strong> + <strong>{data.token_c}</strong>
      </Text>

      <div className="grid grid-cols-4 gap-4 mt-5">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>IDF (corpus)</Text>
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
          <Text size="1" style={{ color: "var(--gray-9)" }}>Phrase / party</Text>
          <Heading size="5" mt="2">
            {(data.n_distinct_phrases / Math.max(1, data.n_party_sides)).toFixed(2)}
          </Heading>
        </div>
      </div>

      <Heading size="4" mt="6" mb="2">Constituent token signals</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <div className="flex flex-wrap gap-2 items-center">
          {data.any_token_distinctive ? <Badge color="jade">any constituent distinctive</Badge> : null}
          {data.all_english ? <Badge color="gray">all common EN/FR</Badge> : null}
          {data.all_place ? <Badge color="blue">all place names</Badge> : null}
          {data.all_industry ? <Badge color="amber">all industry stopwords</Badge> : null}
          {data.any_token_excluded ? <Badge color="red">contains excluded token</Badge> : null}
          {!data.any_token_distinctive && !data.all_english && !data.all_place && !data.all_industry && !data.any_token_excluded
            ? <Badge color="gray">no constituent signal</Badge> : null}
          <Text size="2" style={{ color: "var(--gray-9)", marginLeft: "auto" }}>
            distinctiveness is gated on the trigram's own IDF
          </Text>
        </div>
      </div>

      <Heading size="4" mt="6" mb="2">Brand phrases containing this trigram</Heading>
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
      <div className="flex flex-col gap-3">
        {data.party_sides.map((p) => (
          <PartySideCard key={`${p.source_id}-${p.side}`}
                         partySide={p}
                         highlightToken={data.trigram} />
        ))}
      </div>
    </div>
  );
}
