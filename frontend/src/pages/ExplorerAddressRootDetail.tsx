import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type {
  AddressRootDetail,
  AddressRootSuffixBreakdown,
  AddressRootSuiteBreakdown,
  AddressRootPostalBreakdown,
} from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import AddressTabs from "../components/explorer/AddressTabs";
import PartySideCard from "../components/explorer/PartySideCard";
import AddressUnitsAtRoot from "../components/explorer/AddressUnitsAtRoot";

function formatRoot(r: { street_number: string; street_name: string }) {
  return [r.street_number, r.street_name].filter(Boolean).join(" ");
}

const TRUNC_LIMIT = 50;

export default function ExplorerAddressRootDetail() {
  const { key } = useParams<{ key: string }>();
  const [searchParams] = useSearchParams();
  const city = searchParams.get('city') || '';
  const [data, setData] = useState<AddressRootDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!key) return;
    fetchApi<AddressRootDetail>(`/explorer/addresses/roots/${encodeURIComponent(key)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [key]);

  if (err) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <ExplorerTabs />
        <AddressTabs />
        <Text color="tomato">{err}</Text>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <ExplorerTabs />
        <AddressTabs />
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  const suffixHeading =
    data.by_suffix.length < data.n_distinct_suffixes
      ? `By suffix (${data.n_distinct_suffixes.toLocaleString()} distinct, top ${TRUNC_LIMIT} shown)`
      : `By suffix (${data.n_distinct_suffixes.toLocaleString()} distinct)`;

  const suiteHeading =
    data.by_suite.length < data.n_distinct_suites
      ? `By suite (${data.n_distinct_suites.toLocaleString()} distinct, top ${TRUNC_LIMIT} shown)`
      : `By suite (${data.n_distinct_suites.toLocaleString()} distinct)`;

  const postalHeading =
    data.by_postal.length < data.n_distinct_postals
      ? `By postal (${data.n_distinct_postals.toLocaleString()} distinct, top ${TRUNC_LIMIT} shown)`
      : `By postal (${data.n_distinct_postals.toLocaleString()} distinct)`;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <AddressTabs />
      <Link to="/explorer/addresses/roots" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Address Roots
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-1 flex-wrap">
        <Heading size="6" className="font-mono">{formatRoot(data)}</Heading>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-5">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Party-sides</Text>
          <Heading size="5" mt="2">{data.n_party_sides.toLocaleString()}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Distinct suffixes</Text>
          <Heading size="5" mt="2">{data.n_distinct_suffixes.toLocaleString()}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Distinct suites</Text>
          <Heading size="5" mt="2">{data.n_distinct_suites.toLocaleString()}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Distinct postals</Text>
          <Heading size="5" mt="2">{data.n_distinct_postals.toLocaleString()}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Distinct directions</Text>
          <Heading size="5" mt="2">{data.n_distinct_directions.toLocaleString()}</Heading>
        </div>
      </div>

      <Heading size="4" mt="6" mb="2">{suffixHeading}</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">value</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
            </tr>
          </thead>
          <tbody>
            {data.by_suffix.map((row: AddressRootSuffixBreakdown, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">
                  {row.base_key ? (
                    <Link to={`/explorer/addresses/bases/${encodeURIComponent(row.base_key)}`}
                          className="no-underline"
                          style={{ color: "var(--accent-11)" }}>
                      {row.value}
                    </Link>
                  ) : (
                    <span style={{ color: "var(--gray-11)" }}>{row.value}</span>
                  )}
                </td>
                <td className="p-2 text-right">{row.n_party_sides.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Heading size="4" mt="6" mb="2">{suiteHeading}</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">suite_type</th>
              <th className="text-left p-2 font-medium">suite_number</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
            </tr>
          </thead>
          <tbody>
            {data.by_suite.map((row: AddressRootSuiteBreakdown, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2">
                  {row.suite_type || <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2">
                  {row.suite_number || <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2 text-right">{row.n_party_sides.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Heading size="4" mt="6" mb="2">{postalHeading}</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">postal</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
            </tr>
          </thead>
          <tbody>
            {data.by_postal.map((row: AddressRootPostalBreakdown, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">
                  {row.postal || <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2 text-right">{row.n_party_sides.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {city && key && (
        <AddressUnitsAtRoot rootKey={`${city}|${key}`} />
      )}
      {!city && (
        <Text size="1" style={{ color: "var(--gray-9)" }} className="mt-6 block">
          Tip: append <span className="font-mono">?city=toronto</span> to the URL to see the unit-by-unit breakdown.
        </Text>
      )}

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
