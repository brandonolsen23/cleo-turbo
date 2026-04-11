import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, TextField, Button, Badge, Separator } from "@radix-ui/themes";
import {
  ArrowRight, MagnifyingGlass, Play, Eye, ArrowsClockwise,
  CircleNotch, CheckCircle, Warning, Clock, CloudArrowDown,
} from "@phosphor-icons/react";
import { fetchApi, postApi } from "../api/client";
import { formatNumber } from "../lib/utils";
import type {
  OrchestratorStatus, OrchestratorRunResponse, OrchestratorLogResponse,
  ScraperStatus, ScraperRunResponse,
} from "../types";

/* ------------------------------------------------------------------ */
/* Stage overview types (existing)                                     */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function relativeTime(ts: string) {
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatSecs(s: number) {
  if (s < 60) return `${s.toFixed(0)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export default function PipelineOverviewPage() {
  const navigate = useNavigate();

  /* Stage overview */
  const [stageData, setStageData] = useState<OverviewData | null>(null);
  const [traceId, setTraceId] = useState("");

  /* Orchestrator */
  const [orch, setOrch] = useState<OrchestratorStatus | null>(null);
  const [runLog, setRunLog] = useState<string[]>([]);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  /* Scraper */
  const [scraper, setScraper] = useState<ScraperStatus | null>(null);
  const [scraperLog, setScraperLog] = useState<string[]>([]);
  const [scraperLoading, setScraperLoading] = useState<string | null>(null);
  const [scraperResult, setScraperResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const scraperPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scraperLogEndRef = useRef<HTMLDivElement>(null);

  /* Initial data load */
  useEffect(() => {
    fetchApi<OverviewData>("/pipeline/overview").then(setStageData);
    fetchApi<OrchestratorStatus>("/admin/orchestrator/status").then(setOrch);
    fetchApi<ScraperStatus>("/admin/scraper/status").then(setScraper);
  }, []);

  /* Poll while a run is active */
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(() => {
      fetchApi<OrchestratorStatus>("/admin/orchestrator/status").then((s) => {
        setOrch(s);
        if (!s.running) {
          // Run finished — stop polling, refresh stage data
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setActionLoading(null);
          fetchApi<OverviewData>("/pipeline/overview").then(setStageData);
        }
      });
      fetchApi<OrchestratorLogResponse>("/admin/orchestrator/log", { lines: 80 }).then((r) => {
        setRunLog(r.lines || []);
      });
    }, 3000);
  }, []);

  useEffect(() => {
    // If already running when page loads, start polling
    if (orch?.running) startPolling();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [orch?.running, startPolling]);

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [runLog]);

  /* Actions */
  const runPipeline = async (mode: string, skipResolve = false) => {
    setActionLoading(mode);
    setActionResult(null);
    setRunLog([]);
    try {
      const params: Record<string, string> = { mode };
      if (skipResolve) params.skip_resolve = "true";
      const res = await postApi<OrchestratorRunResponse>(
        `/admin/orchestrator/run?mode=${mode}${skipResolve ? "&skip_resolve=true" : ""}`,
        {},
      );
      if (res.success) {
        setActionResult({ ok: true, msg: res.message });
        startPolling();
      } else {
        setActionResult({ ok: false, msg: "Failed to start" });
        setActionLoading(null);
      }
    } catch (e: any) {
      setActionResult({ ok: false, msg: e?.message || "Request failed" });
      setActionLoading(null);
    }
  };

  /* Scraper polling */
  const startScraperPolling = useCallback(() => {
    if (scraperPollRef.current) return;
    scraperPollRef.current = setInterval(() => {
      fetchApi<ScraperStatus>("/admin/scraper/status").then((s) => {
        setScraper(s);
        if (!s.running) {
          if (scraperPollRef.current) clearInterval(scraperPollRef.current);
          scraperPollRef.current = null;
          setScraperLoading(null);
        }
      });
      fetchApi<{ lines: string[] }>("/admin/scraper/log", { lines: 80 }).then((r) => {
        setScraperLog(r.lines || []);
      });
    }, 3000);
  }, []);

  useEffect(() => {
    if (scraper?.running) startScraperPolling();
    return () => { if (scraperPollRef.current) clearInterval(scraperPollRef.current); };
  }, [scraper?.running, startScraperPolling]);

  useEffect(() => {
    scraperLogEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [scraperLog]);

  const runScraper = async (mode: string, dryRun = false) => {
    const label = dryRun ? `${mode}-dry` : mode;
    setScraperLoading(label);
    setScraperResult(null);
    setScraperLog([]);
    try {
      const res = await postApi<ScraperRunResponse>(
        `/admin/scraper/run?mode=${mode}${dryRun ? "&dry_run=true" : ""}`,
        {},
      );
      if (res.success) {
        setScraperResult({ ok: true, msg: res.message });
        startScraperPolling();
      } else {
        setScraperResult({ ok: false, msg: "Failed to start" });
        setScraperLoading(null);
      }
    } catch (e: any) {
      setScraperResult({ ok: false, msg: e?.message || "Request failed" });
      setScraperLoading(null);
    }
  };

  const isScraperRunning = scraper?.running || !!scraperLoading;

  const handleTrace = () => {
    const id = traceId.trim().toUpperCase();
    if (id && id.startsWith("RT")) navigate(`/pipeline/trace/${id}`);
  };

  const isRunning = orch?.running || !!actionLoading;

  /* -------------------------------------------------------------- */
  /* Render                                                          */
  /* -------------------------------------------------------------- */

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Pipeline Inspector</Heading>
      </div>

      {/* ---- Scraper Controls ---- */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <div className="flex items-center justify-between mb-4">
          <Text size="3" weight="medium">Daily Scraper</Text>
          {scraper?.running && (
            <Badge color="blue" size="1">
              <CircleNotch size={12} className="animate-spin" /> Running
            </Badge>
          )}
        </div>

        {/* Recent run stats */}
        {scraper && scraper.recent_runs.length > 0 && (
          <div className="grid grid-cols-4 gap-3 mb-4">
            <div className="text-center">
              <Text size="1" style={{ color: "var(--gray-9)" }} className="block">Last Run</Text>
              <Text size="2" weight="medium" className="block">
                {relativeTime(scraper.recent_runs[0].completed_at)}
              </Text>
            </div>
            <div className="text-center">
              <Text size="1" style={{ color: "var(--gray-9)" }} className="block">New Found</Text>
              <Text size="4" weight="medium" className="block" style={{ color: scraper.recent_runs[0].new_downloaded > 0 ? "var(--jade-11)" : undefined }}>
                {formatNumber(scraper.recent_runs[0].new_downloaded)}
              </Text>
            </div>
            <div className="text-center">
              <Text size="1" style={{ color: "var(--gray-9)" }} className="block">Already Known</Text>
              <Text size="4" weight="medium" className="block">
                {formatNumber(scraper.recent_runs[0].already_known)}
              </Text>
            </div>
            <div className="text-center">
              <Text size="1" style={{ color: "var(--gray-9)" }} className="block">Total in Range</Text>
              <Text size="4" weight="medium" className="block">
                {formatNumber(scraper.recent_runs[0].total_found)}
              </Text>
            </div>
          </div>
        )}

        <Separator size="4" className="my-3" />

        {/* Scraper action buttons */}
        <div className="flex items-center gap-3 flex-wrap">
          <Button
            size="2"
            variant="solid"
            onClick={() => runScraper("daily")}
            disabled={isScraperRunning}
          >
            {scraperLoading === "daily" ? <CircleNotch size={14} className="animate-spin" /> : <CloudArrowDown size={14} />}
            Daily Scrape
          </Button>

          <Button
            size="2"
            variant="soft"
            onClick={() => runScraper("daily", true)}
            disabled={isScraperRunning}
          >
            <Eye size={14} />
            Dry Run
          </Button>

          <Button
            size="2"
            variant="soft"
            color="violet"
            onClick={() => runScraper("audit")}
            disabled={isScraperRunning}
          >
            <ArrowsClockwise size={14} />
            Audit (90 days)
          </Button>

          {scraperResult && (
            <Badge
              color={scraperResult.ok ? "green" : "red"}
              size="2"
              className="ml-2"
            >
              {scraperResult.ok ? <CheckCircle size={14} /> : <Warning size={14} />}
              {scraperResult.msg}
            </Badge>
          )}
        </div>
      </div>

      {/* ---- Scraper Live Log ---- */}
      {scraperLog.length > 0 && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <div className="flex items-center justify-between mb-3">
            <Text size="3" weight="medium">Scraper Output</Text>
            {scraper?.running && (
              <Badge color="blue" size="1">
                <CircleNotch size={12} className="animate-spin" /> Live
              </Badge>
            )}
          </div>
          <div
            className="font-mono text-[12px] leading-[1.6] overflow-auto rounded-md p-3"
            style={{
              background: "var(--gray-2)",
              color: "var(--gray-12)",
              maxHeight: 320,
            }}
          >
            {scraperLog.map((line, i) => (
              <div key={i} style={{ color: line.includes("ERROR") ? "var(--red-11)" : line.includes("COMPLETE") ? "var(--jade-11)" : undefined }}>
                {line || "\u00A0"}
              </div>
            ))}
            <div ref={scraperLogEndRef} />
          </div>
        </div>
      )}

      {/* ---- Scraper History ---- */}
      {scraper && scraper.recent_runs.length > 1 && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Scraper History</Text>
          <table className="w-full text-[13px]">
            <thead>
              <tr className="bg-[var(--gray-2)]">
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>When</th>
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Mode</th>
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Range</th>
                <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>New</th>
                <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Total</th>
                <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Verify</th>
              </tr>
            </thead>
            <tbody>
              {scraper.recent_runs.map((run, i) => (
                <tr key={i} className="border-t border-[var(--gray-4)]">
                  <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>
                    <div className="flex items-center gap-1.5">
                      <Clock size={13} style={{ color: "var(--gray-8)" }} />
                      {relativeTime(run.completed_at)}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="soft" size="1">{run.dry_run ? `${run.mode} (dry)` : run.mode}</Badge>
                  </td>
                  <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>
                    {run.start_date} → {run.end_date}
                  </td>
                  <td className="px-3 py-2 text-right font-medium" style={{ color: run.new_downloaded > 0 ? "var(--jade-11)" : undefined }}>
                    {formatNumber(run.new_downloaded)}
                  </td>
                  <td className="px-3 py-2 text-right" style={{ color: "var(--gray-9)" }}>
                    {formatNumber(run.total_found)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {run.dry_run ? (
                      <span style={{ color: "var(--gray-8)" }}>—</span>
                    ) : run.verification_ok ? (
                      <Badge color="green" size="1">Pass</Badge>
                    ) : (
                      <Badge color="red" size="1">Fail</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ---- Control Panel ---- */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <div className="flex items-center justify-between mb-4">
          <Text size="3" weight="medium">Pipeline Controls</Text>
          {orch && (
            <div className="flex items-center gap-3 text-[12px]" style={{ color: "var(--gray-9)" }}>
              {orch.resolve_locked && (
                <Badge color="amber" size="1">Resolve Locked (PID {orch.resolve_pid})</Badge>
              )}
              {orch.reprocess && (
                <Badge color="violet" size="1">Reprocessing from {orch.reprocess.from_stage}</Badge>
              )}
              {orch.running && (
                <Badge color="blue" size="1">
                  <CircleNotch size={12} className="animate-spin" /> Running
                </Badge>
              )}
            </div>
          )}
        </div>

        {/* Stage counts + pending */}
        {orch && (
          <div className="grid grid-cols-6 gap-3 mb-4">
            {(["assembled", "deduped", "classified", "normalized", "resolved", "clean_data"] as const).map(
              (key) => {
                const count = orch.stages[key];
                const pendingMap: Record<string, number> = {
                  deduped: orch.pending.dedup,
                  classified: orch.pending.classify,
                  normalized: orch.pending.normalize,
                  resolved: orch.pending.resolve,
                };
                const pending = pendingMap[key] || 0;
                const label = key === "clean_data" ? "Clean Data" : key.charAt(0).toUpperCase() + key.slice(1);
                return (
                  <div key={key} className="text-center">
                    <Text size="1" style={{ color: "var(--gray-9)" }} className="block">{label}</Text>
                    <Text size="4" weight="medium" className="block">{formatNumber(count)}</Text>
                    {pending > 0 && (
                      <Badge color="amber" size="1" className="mt-1">{formatNumber(pending)} pending</Badge>
                    )}
                  </div>
                );
              },
            )}
          </div>
        )}

        <Separator size="4" className="my-3" />

        {/* Action buttons */}
        <div className="flex items-center gap-3 flex-wrap">
          <Button
            size="2"
            variant="solid"
            onClick={() => runPipeline("new")}
            disabled={isRunning}
          >
            {actionLoading === "new" ? <CircleNotch size={14} className="animate-spin" /> : <Play size={14} />}
            Process New
          </Button>

          <Button
            size="2"
            variant="soft"
            onClick={() => runPipeline("dry-run")}
            disabled={isRunning}
          >
            <Eye size={14} />
            Dry Run
          </Button>

          <Button
            size="2"
            variant="soft"
            color="violet"
            onClick={() => runPipeline("from-classify", true)}
            disabled={isRunning}
          >
            <ArrowsClockwise size={14} />
            Reprocess (skip resolve)
          </Button>

          {actionResult && (
            <Badge
              color={actionResult.ok ? "green" : "red"}
              size="2"
              className="ml-2"
            >
              {actionResult.ok ? <CheckCircle size={14} /> : <Warning size={14} />}
              {actionResult.msg}
            </Badge>
          )}
        </div>
      </div>

      {/* ---- Live Log ---- */}
      {runLog.length > 0 && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <div className="flex items-center justify-between mb-3">
            <Text size="3" weight="medium">Run Output</Text>
            {orch?.running && (
              <Badge color="blue" size="1">
                <CircleNotch size={12} className="animate-spin" /> Live
              </Badge>
            )}
          </div>
          <div
            className="font-mono text-[12px] leading-[1.6] overflow-auto rounded-md p-3"
            style={{
              background: "var(--gray-2)",
              color: "var(--gray-12)",
              maxHeight: 320,
            }}
          >
            {runLog.map((line, i) => (
              <div key={i} style={{ color: line.includes("ERROR") ? "var(--red-11)" : undefined }}>
                {line || "\u00A0"}
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {/* ---- Processing History ---- */}
      {orch && orch.log.length > 0 && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Processing History</Text>
          <table className="w-full text-[13px]">
            <thead>
              <tr className="bg-[var(--gray-2)]">
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>When</th>
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Stage</th>
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Mode</th>
                <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Processed</th>
                <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Time</th>
                <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Errors</th>
              </tr>
            </thead>
            <tbody>
              {[...orch.log].reverse().slice(0, 15).map((entry, i) => (
                <tr key={i} className="border-t border-[var(--gray-4)]">
                  <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>
                    <div className="flex items-center gap-1.5">
                      <Clock size={13} style={{ color: "var(--gray-8)" }} />
                      {relativeTime(entry.timestamp)}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="soft" size="1">{entry.stage}</Badge>
                  </td>
                  <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>{entry.mode}</td>
                  <td className="px-3 py-2 text-right font-medium">{formatNumber(entry.files_processed)}</td>
                  <td className="px-3 py-2 text-right" style={{ color: "var(--gray-9)" }}>{formatSecs(entry.elapsed_seconds)}</td>
                  <td className="px-3 py-2 text-right">
                    {entry.errors > 0 ? (
                      <Badge color="red" size="1">{entry.errors}</Badge>
                    ) : (
                      <span style={{ color: "var(--gray-8)" }}>0</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ---- RT ID Trace search ---- */}
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

      {/* ---- Stage flow ---- */}
      {stageData && (
        <div className="flex flex-col gap-3">
          <Text size="3" weight="medium">Pipeline Stages</Text>
          <div className="flex items-stretch gap-2 overflow-x-auto pb-2">
            {stageData.stages.map((stage, i) => (
              <div key={stage.name} className="flex items-center gap-2">
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

                {i < stageData.stages.length - 1 && (
                  <ArrowRight size={16} style={{ color: "var(--gray-8)", flexShrink: 0 }} />
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
