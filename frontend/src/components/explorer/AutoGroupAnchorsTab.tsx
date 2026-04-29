import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type {
  AutoGroupAnchorsWithCoverageResponse,
  AutoGroupAnchorWithCoverage,
} from "../../types";


function silosLinkFor(a: AutoGroupAnchorWithCoverage): string | null {
  if (a.anchor_type === 'phone') return `/explorer/phones/${encodeURIComponent(a.anchor_value)}`;
  if (a.anchor_type === 'address_unit') return `/explorer/addresses/units/${encodeURIComponent(a.anchor_value)}`;
  if (a.anchor_type === 'contact') return `/explorer/contacts/${encodeURIComponent(a.anchor_value)}`;
  return null;
}


export default function AutoGroupAnchorsTab({ autoGroupId }: { autoGroupId: string }) {
  const [data, setData] = useState<AutoGroupAnchorsWithCoverageResponse | null>(null);

  useEffect(() => {
    fetchApi<AutoGroupAnchorsWithCoverageResponse>(
      `/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/anchors-with-coverage`,
    ).then(setData).catch(console.error);
  }, [autoGroupId]);

  if (!data) {
    return <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>;
  }

  return (
    <>
      <Heading size="4" mb="2">Anchors ({data.anchors.length})</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">type</th>
              <th className="text-left p-2 font-medium">value</th>
              <th className="text-right p-2 font-medium">score</th>
              <th className="text-right p-2 font-medium">coverage</th>
              <th className="text-left p-2 font-medium">co-stems</th>
              <th className="text-left p-2 font-medium">silo</th>
            </tr>
          </thead>
          <tbody>
            {data.anchors.map((a, i) => {
              const link = silosLinkFor(a);
              return (
                <tr key={i} className="border-t border-[var(--gray-4)]">
                  <td className="p-2">{a.anchor_type}</td>
                  <td className="p-2 font-mono">{a.anchor_value}</td>
                  <td className="p-2 text-right">{a.score.toFixed(2)}</td>
                  <td className="p-2 text-right">{a.coverage.toLocaleString()}</td>
                  <td className="p-2">
                    {a.co_stems.length === 0
                      ? <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>
                      : a.co_stems.map((c, j) => (
                          <Badge key={j} color="amber" className="mr-1 mb-1">
                            {c.stem} ({c.n_parties})
                          </Badge>
                        ))
                    }
                  </td>
                  <td className="p-2">
                    {link ? (
                      <Link to={link} className="no-underline"
                            style={{ color: "var(--accent-11)" }}>
                        view
                      </Link>
                    ) : (
                      <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
