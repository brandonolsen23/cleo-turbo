import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, TextField, Button } from "@radix-ui/themes";
import { ArrowRight, MagnifyingGlass } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatNumber } from "../lib/utils";

interface StageHealth {
  sample_size: number;
  metrics: Record<string, any>;
}

interface StageInfo {
  name: string;
  label: string;
  file_count: number;
  health: StageHealth | null;
}

interface OverviewData {
  stages: StageInfo[];
  cached_at: string;
}

export default function PipelineOverviewPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OverviewData | null>(null);
  const [traceId, setTraceId] = useState("");

  useEffect(() => {
    fetchApi<OverviewData>("/pipeline/overview").then(setData);
  }, []);

  const handleTrace = () => {
    const id = traceId.trim().toUpperCase();
    if (id && id.startsWith("RT")) navigate(`/pipeline/trace/${id}`);
  };

  if (!data) return <Text>Loading pipeline data...</Text>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Pipeline Inspector</Heading>
      </div>

      {/* RT ID Trace search */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Text size="3" weight="medium" className="mb-3 block">Trace an RT ID</Text>
        <div className="flex gap-2">
          <TextField.Root
            value={traceId}
            onChange={(e: any) => setTraceId(e.target.value)}
            onKeyDown={(e: any) => e.key === "Enter" && handleTrace()}
            placeholder="Enter RT ID (e.g. RT100002)"
            size="2"
            className="flex-1"
          />
          <Button size="2" onClick={handleTrace} disabled={!traceId.trim()}>
            <MagnifyingGlass size={14} />
            Trace
          </Button>
        </div>
      </div>

      {/* Stage flow */}
      <div className="flex flex-col gap-3">
        <Text size="3" weight="medium">Pipeline Stages</Text>
        <div className="flex items-stretch gap-2 overflow-x-auto pb-2">
          {data.stages.map((stage, i) => (
            <div key={stage.name} className="flex items-center gap-2">
              {/* Stage card */}
              <div
                className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 cursor-pointer hover:border-[var(--gray-8)] transition-colors"
                style={{ minWidth: 180 }}
                onClick={() => navigate(`/pipeline/${stage.name}`)}
              >
                <Text size="1" weight="medium" className="block" style={{ color: "var(--gray-9)" }}>
                  {stage.label}
                </Text>
                <Heading size="5" weight="medium" className="mt-1">
                  {formatNumber(stage.file_count)}
                </Heading>

                {/* Health metrics */}
                {stage.health && stage.name === "assembled" && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-[12px] mb-1">
                      <span style={{ color: "var(--gray-9)" }}>Join Verified</span>
                      <span className="font-medium" style={{ color: "var(--green-11)" }}>
                        {(stage.health.metrics.join_verified?.rate * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full" style={{ background: "var(--gray-4)" }}>
                      <div className="h-1.5 rounded-full" style={{
                        background: "var(--green-9)",
                        width: `${(stage.health.metrics.join_verified?.rate ?? 0) * 100}%`,
                      }} />
                    </div>
                  </div>
                )}

                {stage.health && stage.name === "addresses" && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-[12px] mb-1">
                      <span style={{ color: "var(--gray-9)" }}>Geocodable</span>
                      <span className="font-medium" style={{ color: "var(--green-11)" }}>
                        {(stage.health.metrics.geocodable?.rate * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full" style={{ background: "var(--gray-4)" }}>
                      <div className="h-1.5 rounded-full" style={{
                        background: "var(--green-9)",
                        width: `${(stage.health.metrics.geocodable?.rate ?? 0) * 100}%`,
                      }} />
                    </div>
                  </div>
                )}

                {stage.health && stage.name === "parcel_links" && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-[12px] mb-1">
                      <span style={{ color: "var(--gray-9)" }}>Resolved</span>
                      <span className="font-medium" style={{ color: "var(--jade-11)" }}>
                        {((stage.health.metrics.resolved_rate ?? 0) * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full" style={{ background: "var(--gray-4)" }}>
                      <div className="h-1.5 rounded-full" style={{
                        background: "var(--jade-9)",
                        width: `${(stage.health.metrics.resolved_rate ?? 0) * 100}%`,
                      }} />
                    </div>
                    <div className="flex gap-2 mt-2 text-[11px]" style={{ color: "var(--gray-9)" }}>
                      {Object.entries(stage.health.metrics.method || {}).map(([k, v]) => (
                        <span key={k}>{k}: {v as number}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Arrow between stages */}
              {i < data.stages.length - 1 && (
                <ArrowRight size={16} style={{ color: "var(--gray-8)", flexShrink: 0 }} />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
