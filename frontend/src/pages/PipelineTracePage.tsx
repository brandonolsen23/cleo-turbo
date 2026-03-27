import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, TextField, Button, Badge } from "@radix-ui/themes";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import JsonTree from "../components/pipeline/JsonTree";
import PipelineFlowView from "../components/pipeline/PipelineFlowView";

interface TraceClassification {
  source_folder: string;
  position: number;
  region: string;
  property_type: string;
  page: string;
}

interface StageEntry {
  filename: string;
  data: Record<string, unknown>;
  file_size?: number;
  modified_at?: string;
}

interface ExtractedEntry {
  source_folder: string;
  position: number;
  files: Record<string, { filename: string; data?: Record<string, unknown>; error?: string }>;
}

interface RawEntry {
  source_folder: string;
  position: number;
  files: Record<string, { filename: string; exists: boolean; file_size?: number }>;
}

interface TraceData {
  rt_id: string;
  classifications: TraceClassification[];
  stages: {
    raw: RawEntry[];
    extracted: ExtractedEntry[];
    assembled: StageEntry[];
    classified: StageEntry[];
    addresses: StageEntry[];
    parcel_links: StageEntry[];
    clean: StageEntry | null;
  };
}

interface DiffChange {
  path: string;
  type: "added" | "removed" | "changed";
  value?: unknown;
  old?: unknown;
  new?: unknown;
}

interface DiffResponse {
  changes: DiffChange[];
  summary: { added: number; removed: number; changed: number; total: number };
}

const STAGE_TABS = [
  { key: "raw", label: "Raw" },
  { key: "extracted", label: "Extracted" },
  { key: "assembled", label: "Assembled" },
  { key: "classified", label: "Classified" },
  { key: "addresses", label: "Addresses" },
  { key: "parcel_links", label: "Parcel Links" },
  { key: "clean", label: "Clean" },
];

const DIFFABLE_PAIRS: [string, string][] = [
  ["assembled", "classified"],
  ["classified", "addresses"],
];

export default function PipelineTracePage() {
  const { rtId } = useParams();
  const navigate = useNavigate();
  const [trace, setTrace] = useState<TraceData | null>(null);
  const [viewMode, setViewMode] = useState<"stages" | "flow">("flow");
  const [activeTab, setActiveTab] = useState("assembled");
  const [searchId, setSearchId] = useState("");
  const [showDiff, setShowDiff] = useState(false);
  const [diffData, setDiffData] = useState<DiffResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [rawHtml, setRawHtml] = useState<string | null>(null);

  useEffect(() => {
    if (rtId) {
      setLoading(true);
      setShowDiff(false);
      setDiffData(null);
      fetchApi<TraceData>(`/pipeline/trace/${rtId}`).then((d) => {
        setTrace(d);
        setLoading(false);
        // Fetch raw HTML for flow view
        if (d.classifications.length > 0) {
          const cls = d.classifications[0];
          fetchApi<{ content: string }>(`/pipeline/raw-preview/${cls.source_folder}/${cls.position}`)
            .then((r) => setRawHtml(r.content))
            .catch(() => setRawHtml(null));
        }
      });
    }
  }, [rtId]);

  const handleSearch = () => {
    const id = searchId.trim().toUpperCase();
    if (id && id.startsWith("RT")) navigate(`/pipeline/trace/${id}`);
  };

  const canDiff = DIFFABLE_PAIRS.some(([, to]) => to === activeTab);
  const diffFrom = DIFFABLE_PAIRS.find(([, to]) => to === activeTab)?.[0];

  const handleDiffToggle = async () => {
    if (showDiff) {
      setShowDiff(false);
      setDiffData(null);
      return;
    }
    if (!diffFrom || !rtId) return;
    setShowDiff(true);
    const data = await fetchApi<DiffResponse>(`/pipeline/diff/${rtId}`, {
      stage_from: diffFrom,
      stage_to: activeTab,
    });
    setDiffData(data);
  };

  if (loading) return <Text>Loading trace for {rtId}...</Text>;
  if (!trace) return <Text>No data found for {rtId}</Text>;

  const getStageData = () => {
    switch (activeTab) {
      case "raw": return trace.stages.raw;
      case "extracted": return trace.stages.extracted;
      case "assembled": return trace.stages.assembled;
      case "classified": return trace.stages.classified;
      case "addresses": return trace.stages.addresses;
      case "parcel_links": return trace.stages.parcel_links;
      case "clean": return trace.stages.clean ? [trace.stages.clean] : [];
      default: return [];
    }
  };

  const stageData = getStageData();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link to="/pipeline" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
          &larr; Pipeline
        </Link>
        <div className="flex items-center gap-4 mt-2">
          <Heading size="5" weight="medium" className="font-mono">{trace.rt_id}</Heading>
          {trace.classifications.length > 0 && (
            <div className="flex gap-1">
              {trace.classifications.map((c, i) => (
                <Badge key={i} size="1" variant="soft">
                  {c.region?.replace(/_/g, " ")} / {c.property_type}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Search + view toggle */}
      <div className="flex items-center gap-3">
        <div className="flex gap-2 flex-1" style={{ maxWidth: 340 }}>
          <TextField.Root
            value={searchId}
            onChange={(e: any) => setSearchId(e.target.value)}
            onKeyDown={(e: any) => e.key === "Enter" && handleSearch()}
            placeholder="Jump to another RT ID..."
            size="2"
            className="flex-1"
          />
          <Button size="2" variant="soft" onClick={handleSearch} disabled={!searchId.trim()}>
            <MagnifyingGlass size={14} />
          </Button>
        </div>
        <div className="ml-auto flex rounded-lg border overflow-hidden" style={{ borderColor: "var(--gray-6)" }}>
          <button
            className="px-3 py-1.5 text-[13px] transition-colors"
            style={{
              background: viewMode === "stages" ? "var(--jade-9)" : "white",
              color: viewMode === "stages" ? "white" : "var(--gray-11)",
              fontWeight: viewMode === "stages" ? 500 : 400,
            }}
            onClick={() => setViewMode("stages")}
          >
            Stage View
          </button>
          <button
            className="px-3 py-1.5 text-[13px] border-l transition-colors"
            style={{
              borderColor: "var(--gray-6)",
              background: viewMode === "flow" ? "var(--jade-9)" : "white",
              color: viewMode === "flow" ? "white" : "var(--gray-11)",
              fontWeight: viewMode === "flow" ? 500 : 400,
            }}
            onClick={() => setViewMode("flow")}
          >
            Flow View
          </button>
        </div>
      </div>

      {/* Flow View */}
      {viewMode === "flow" && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
          <PipelineFlowView trace={trace} rawHtml={rawHtml} />
        </div>
      )}

      {/* Stage View (tab-based) */}
      {viewMode === "stages" && <>
      <div className="flex gap-1 border-b" style={{ borderColor: "var(--gray-4)" }}>
        {STAGE_TABS.map((tab) => {
          const isActive = tab.key === activeTab;
          const hasData = (() => {
            const d = trace.stages[tab.key as keyof typeof trace.stages];
            if (Array.isArray(d)) return d.length > 0;
            return d !== null;
          })();
          return (
            <button
              key={tab.key}
              onClick={() => { setActiveTab(tab.key); setShowDiff(false); setDiffData(null); }}
              className="px-3 py-2 text-[14px] border-b-2 transition-colors"
              style={{
                borderColor: isActive ? "var(--jade-9)" : "transparent",
                color: isActive ? "var(--gray-12)" : hasData ? "var(--gray-11)" : "var(--gray-8)",
                fontWeight: isActive ? 500 : 400,
                background: "transparent",
              }}
            >
              {tab.label}
              {!hasData && <span className="ml-1 text-[11px]" style={{ color: "var(--gray-8)" }}>-</span>}
            </button>
          );
        })}
      </div>

      {/* Diff toggle */}
      {canDiff && (
        <div className="flex items-center gap-3">
          <Button size="1" variant={showDiff ? "solid" : "soft"} onClick={handleDiffToggle}>
            {showDiff ? "Hide Diff" : `Show Diff from ${diffFrom}`}
          </Button>
          {showDiff && diffData && (
            <div className="flex gap-2 text-[12px]">
              <Badge size="1" color="green" variant="soft">+{diffData.summary.added} added</Badge>
              <Badge size="1" color="red" variant="soft">-{diffData.summary.removed} removed</Badge>
              <Badge size="1" color="amber" variant="soft">~{diffData.summary.changed} changed</Badge>
            </div>
          )}
        </div>
      )}

      {/* Stage content */}
      {activeTab === "raw" && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          {(stageData as RawEntry[]).length === 0 ? (
            <Text size="2" style={{ color: "var(--gray-9)" }}>No raw files found</Text>
          ) : (
            (stageData as RawEntry[]).map((entry, i) => (
              <div key={i}>
                <Text size="2" weight="medium" className="mb-2 block">{entry.source_folder}</Text>
                <div className="flex flex-col gap-1">
                  {Object.entries(entry.files).map(([key, f]) => (
                    <div key={key} className="flex items-center gap-2 text-[13px]">
                      <Badge size="1" variant={f.exists ? "soft" : "outline"} color={f.exists ? "green" : "red"}>
                        {f.exists ? "exists" : "missing"}
                      </Badge>
                      <span className="font-mono">{f.filename}</span>
                      {f.file_size && (
                        <span style={{ color: "var(--gray-8)" }}>
                          ({(f.file_size / 1024).toFixed(1)} KB)
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === "extracted" && (
        <div className="flex flex-col gap-4">
          {(stageData as ExtractedEntry[]).length === 0 ? (
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
              <Text size="2" style={{ color: "var(--gray-9)" }}>No extracted files found</Text>
            </div>
          ) : (
            (stageData as ExtractedEntry[]).map((entry, i) => (
              <div key={i}>
                <Text size="2" weight="medium" className="mb-2 block">
                  {entry.source_folder} (position {entry.position})
                </Text>
                {Object.entries(entry.files).map(([key, f]) => (
                  <div key={key} className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4 mb-2">
                    <Text size="1" weight="medium" className="mb-2 block" style={{ color: "var(--gray-9)" }}>
                      {f.filename}
                    </Text>
                    {f.data ? (
                      <JsonTree data={f.data} defaultExpand={2} />
                    ) : (
                      <Text size="2" style={{ color: "var(--red-9)" }}>{f.error || "No data"}</Text>
                    )}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      )}

      {["assembled", "classified", "addresses", "parcel_links", "clean"].includes(activeTab) && (
        <div className="flex flex-col gap-4">
          {(stageData as StageEntry[]).length === 0 ? (
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
              <Text size="2" style={{ color: "var(--gray-9)" }}>No record at this stage</Text>
            </div>
          ) : (
            (stageData as StageEntry[]).map((entry, i) => (
              <div key={i} className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Text size="1" weight="medium" className="font-mono" style={{ color: "var(--gray-9)" }}>
                    {entry.filename}
                  </Text>
                  {entry.file_size && (
                    <Text size="1" style={{ color: "var(--gray-8)" }}>
                      ({(entry.file_size / 1024).toFixed(1)} KB)
                    </Text>
                  )}
                </div>
                <JsonTree
                  data={entry.data}
                  defaultExpand={3}
                  changes={showDiff && diffData ? diffData.changes : undefined}
                />
              </div>
            ))
          )}
        </div>
      )}
      </>}
    </div>
  );
}
