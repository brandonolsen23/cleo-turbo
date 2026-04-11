import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Button, TextField, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";

interface BrowseItem {
  filename: string;
  rt_id: string | null;
  region: string | null;
  property_type: string | null;
  page: string | null;
  position: string | null;
}

interface BrowseResponse {
  stage: string;
  results: BrowseItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

const STAGE_LABELS: Record<string, string> = {
  assembled: "Assembled", classified: "Classified", addresses: "Addresses",
  parcel_links: "Parcel Links", clean: "Clean Records",
};

export default function PipelineStagePage() {
  const { stage } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseResponse | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [submitted, setSubmitted] = useState("");

  useEffect(() => {
    if (!stage) return;
    const params: Record<string, string> = { page: String(page), per_page: "50" };
    if (submitted) params.search = submitted;
    fetchApi<BrowseResponse>(`/pipeline/stages/${stage}`, params).then(setData);
  }, [stage, page, submitted]);

  const handleSearch = () => {
    setSubmitted(search);
    setPage(1);
  };

  if (!data) return <Text>Loading...</Text>;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link to="/pipeline" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
          &larr; Pipeline
        </Link>
        <div className="flex items-center justify-between mt-2">
          <Heading size="5" weight="medium">{STAGE_LABELS[stage || ""] || stage}</Heading>
          <Text size="2" style={{ color: "var(--gray-9)" }}>{data.total.toLocaleString()} records</Text>
        </div>
      </div>

      <div className="flex gap-2">
        <TextField.Root
          value={search}
          onChange={(e: any) => setSearch(e.target.value)}
          onKeyDown={(e: any) => e.key === "Enter" && handleSearch()}
          placeholder="Filter by RT ID, region, type..."
          size="2"
          className="flex-1"
        />
        <Button size="2" onClick={handleSearch}>Filter</Button>
        {submitted && (
          <Button size="2" variant="soft" onClick={() => { setSearch(""); setSubmitted(""); setPage(1); }}>Clear</Button>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>RT ID</th>
              {stage !== "clean" && (
                <>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Region</th>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Type</th>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Page</th>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Position</th>
                </>
              )}
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((r) => (
              <tr key={r.filename}
                  className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                  onClick={() => navigate(`/pipeline/${stage}/${r.filename}`)}>
                <td className="px-4 py-2 font-medium font-mono text-[13px]">{r.rt_id || r.filename}</td>
                {stage !== "clean" && (
                  <>
                    <td className="px-4 py-2">{r.region?.replace(/_/g, " ") || "—"}</td>
                    <td className="px-4 py-2">
                      {r.property_type ? (
                        <Badge size="1" variant="soft">{r.property_type}</Badge>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-2" style={{ color: "var(--gray-9)" }}>{r.page || "—"}</td>
                    <td className="px-4 py-2" style={{ color: "var(--gray-9)" }}>{r.position || "—"}</td>
                  </>
                )}
                <td className="px-4 py-2 text-right">
                  {r.rt_id && (
                    <Badge size="1" variant="outline" color="jade" className="cursor-pointer"
                           onClick={(e: any) => { e.stopPropagation(); navigate(`/pipeline/trace/${r.rt_id}`); }}>
                      Trace
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <Text size="2" style={{ color: "var(--gray-9)" }}>Page {data.page} of {data.pages}</Text>
        <div className="flex gap-2">
          <Button size="1" variant="soft" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <Button size="1" variant="soft" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}
