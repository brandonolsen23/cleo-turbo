import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge } from "@radix-ui/themes";
import { Database, MapPin, Storefront, Globe } from "@phosphor-icons/react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { fetchApi, mutateApi, postApi } from "../api/client";
import { formatDate } from "../lib/utils";

interface Summary {
  total_issues: number;
  open_issues: number;
  by_rule: Record<string, number>;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  by_origin_stage: Record<string, number>;
  last_scan: string | null;
}

interface IssueItem {
  id: number;
  source_id: string;
  rule: string;
  severity: string;
  field_path: string;
  actual_value: string | null;
  message: string;
  introduced_at: string | null;
  origin_field: string | null;
  source_field: string | null;
  explanation: string | null;
  code_location: string | null;
  status: string;
  notes: string | null;
  created_at: string;
}

interface BrowseResponse {
  results: IssueItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

const SEVERITY_COLORS: Record<string, any> = {
  error: "red", warning: "amber", info: "blue",
};

interface FreshnessSource {
  source: string;
  label: string;
  status: "green" | "amber" | "red";
  headline: string;
  details: string[];
  checked_at: string;
}

interface FreshnessResponse {
  checked_at: string;
  sources: FreshnessSource[];
}

const FRESHNESS_BADGE: Record<string, { color: any; label: string }> = {
  green: { color: "jade", label: "Flowing" },
  amber: { color: "amber", label: "Attention" },
  red: { color: "red", label: "Stalled" },
};

const SOURCE_ICONS: Record<string, any> = {
  rt: Database,
  gw: MapPin,
  pois: Storefront,
  portfolio: Globe,
};

interface JoinHealthMetric {
  key: string;
  label: string;
  numerator: number;
  denominator: number;
  pct: number;
  detail: string;
}

interface JoinHealthResponse {
  checked_at: string;
  metrics: JoinHealthMetric[];
}

export default function DataQualityPage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [freshness, setFreshness] = useState<FreshnessResponse | null>(null);
  const [joinHealth, setJoinHealth] = useState<JoinHealthResponse | null>(null);
  const [issues, setIssues] = useState<BrowseResponse | null>(null);
  const [page, setPage] = useState(1);
  const [ruleFilter, setRuleFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("open");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [flagNotes, setFlagNotes] = useState<Record<number, string>>({});

  const loadSummary = () => fetchApi<Summary>("/data-quality/summary").then(setSummary);
  const loadIssues = () => {
    const params: Record<string, string> = { page: String(page), per_page: "25", status: statusFilter || "open" };
    if (ruleFilter) params.rule = ruleFilter;
    if (severityFilter) params.severity = severityFilter;
    if (stageFilter) params.introduced_at = stageFilter;
    fetchApi<BrowseResponse>("/data-quality/issues", params).then(setIssues);
  };

  useEffect(() => {
    loadSummary();
    fetchApi<FreshnessResponse>("/data-quality/freshness").then(setFreshness).catch(() => {});
    fetchApi<JoinHealthResponse>("/data-quality/join-health").then(setJoinHealth).catch(() => {});
  }, []);
  useEffect(() => { loadIssues(); }, [page, ruleFilter, severityFilter, stageFilter, statusFilter]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await fetchApi("/data-quality/scan");
      loadSummary();
      loadIssues();
    } finally {
      setScanning(false);
    }
  };

  const handleStatusChange = async (id: number, status: string) => {
    await mutateApi(`/data-quality/issues/${id}`, "PATCH", { status });
    loadIssues();
    loadSummary();
  };

  const handleFlag = async (id: number) => {
    await postApi(`/data-quality/issues/${id}/flag`, { notes: flagNotes[id] || "" });
    // Update the item in place — mark it as flagged without reloading the list
    if (issues) {
      const updated = issues.results.map((i) =>
        i.id === id ? { ...i, status: "flagged", notes: flagNotes[id] || "" } : i
      );
      setIssues({ ...issues, results: updated });
    }
    loadSummary();
  };

  if (!summary) return <Text>Loading...</Text>;

  const ruleChartData = Object.entries(summary.by_rule)
    .slice(0, 10)
    .map(([rule, count]) => ({ name: rule.replace(/_/g, " "), count }));

  const originChartData = Object.entries(summary.by_origin_stage)
    .map(([stage, count]) => ({ name: stage || "unknown", count }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Data Quality</Heading>
        <div className="flex items-center gap-3">
          {summary.last_scan && (
            <Text size="1" style={{ color: "var(--gray-8)" }}>Last scan: {formatDate(summary.last_scan)}</Text>
          )}
          <Button size="2" onClick={handleScan} disabled={scanning}>
            {scanning ? "Scanning..." : "Run Scan"}
          </Button>
        </div>
      </div>

      {/* Source freshness */}
      <div className="flex flex-col gap-3">
        <Heading size="4" weight="medium">Source Freshness</Heading>
        <div className="grid grid-cols-4 gap-4">
          {(freshness?.sources ?? []).map((s) => {
            const badge = FRESHNESS_BADGE[s.status] ?? FRESHNESS_BADGE.red;
            const Icon = SOURCE_ICONS[s.source] ?? Database;
            return (
              <div key={s.source} className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Icon size={16} style={{ color: "var(--gray-9)" }} />
                    <Text size="2" weight="medium">{s.label}</Text>
                  </div>
                  <Badge size="1" color={badge.color} variant="soft">{badge.label}</Badge>
                </div>
                <Text size="2" weight="medium" className="block">{s.headline}</Text>
                <div className="flex flex-col gap-1">
                  {s.details.map((d, i) => (
                    <Text key={i} size="1" className="block" style={{ color: "var(--gray-11)" }}>{d}</Text>
                  ))}
                </div>
              </div>
            );
          })}
          {!freshness && (
            <Text size="2" style={{ color: "var(--gray-8)" }}>Checking sources...</Text>
          )}
        </div>
      </div>

      {/* Join health */}
      <div className="flex flex-col gap-3">
        <Heading size="4" weight="medium">Join Health</Heading>
        <div className="grid grid-cols-5 gap-4">
          {(joinHealth?.metrics ?? []).map((m) => (
            <div key={m.key} className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 flex flex-col gap-2">
              <Text size="2" weight="medium">{m.label}</Text>
              <div className="flex items-baseline gap-2">
                <Heading size="6" weight="medium">{m.pct.toFixed(1)}%</Heading>
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  {m.numerator.toLocaleString()} / {m.denominator.toLocaleString()}
                </Text>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--gray-4)" }}>
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.min(100, Math.max(0, m.pct))}%`, background: "var(--jade-9)" }}
                />
              </div>
              <Text size="1" className="block" style={{ color: "var(--gray-11)" }}>{m.detail}</Text>
            </div>
          ))}
          {!joinHealth && (
            <Text size="2" style={{ color: "var(--gray-8)" }}>Checking joins...</Text>
          )}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="2" style={{ color: "var(--gray-9)" }}>Open Issues</Text>
          <Heading size="6" weight="medium" className="mt-1" style={{ color: summary.open_issues > 0 ? "var(--red-11)" : "var(--green-11)" }}>
            {summary.open_issues.toLocaleString()}
          </Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="2" style={{ color: "var(--gray-9)" }}>Errors</Text>
          <Heading size="6" weight="medium" className="mt-1" style={{ color: "var(--red-11)" }}>
            {(summary.by_severity.error || 0).toLocaleString()}
          </Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="2" style={{ color: "var(--gray-9)" }}>Warnings</Text>
          <Heading size="6" weight="medium" className="mt-1" style={{ color: "var(--amber-11)" }}>
            {(summary.by_severity.warning || 0).toLocaleString()}
          </Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="2" style={{ color: "var(--gray-9)" }}>Info</Text>
          <Heading size="6" weight="medium" className="mt-1" style={{ color: "var(--blue-11)" }}>
            {(summary.by_severity.info || 0).toLocaleString()}
          </Heading>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Issues by Rule</Text>
          {ruleChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={ruleChartData} layout="vertical" margin={{ left: 100, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-4)" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} />
                <Tooltip />
                <Bar dataKey="count" fill="var(--red-9)" radius={[0, 3, 3, 0]} barSize={16} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <Text size="2" style={{ color: "var(--gray-8)" }}>No issues</Text>
          )}
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Issues by Origin Stage</Text>
          {originChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={originChartData} margin={{ left: 10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-4)" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="var(--amber-9)" radius={[3, 3, 0, 0]} barSize={32} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <Text size="2" style={{ color: "var(--gray-8)" }}>No issues</Text>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <select value={ruleFilter} onChange={(e) => { setRuleFilter(e.target.value); setPage(1); }}
          className="h-8 px-2 text-[13px] rounded border bg-white" style={{ borderColor: "var(--gray-6)" }}>
          <option value="">All Rules</option>
          {Object.keys(summary.by_rule).map((r) => (
            <option key={r} value={r}>{r.replace(/_/g, " ")} ({summary.by_rule[r]})</option>
          ))}
        </select>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="h-8 px-2 text-[13px] rounded border bg-white" style={{ borderColor: "var(--gray-6)" }}>
          <option value="open">Open</option>
          <option value="flagged">Flagged for Review</option>
          <option value="resolved">Resolved</option>
          <option value="ignored">Ignored</option>
          <option value="false_positive">False Positive</option>
        </select>
        <select value={severityFilter} onChange={(e) => { setSeverityFilter(e.target.value); setPage(1); }}
          className="h-8 px-2 text-[13px] rounded border bg-white" style={{ borderColor: "var(--gray-6)" }}>
          <option value="">All Severities</option>
          <option value="error">Error</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <select value={stageFilter} onChange={(e) => { setStageFilter(e.target.value); setPage(1); }}
          className="h-8 px-2 text-[13px] rounded border bg-white" style={{ borderColor: "var(--gray-6)" }}>
          <option value="">All Stages</option>
          {Object.keys(summary.by_origin_stage).map((s) => (
            <option key={s} value={s}>{s} ({summary.by_origin_stage[s]})</option>
          ))}
        </select>
        {(ruleFilter || severityFilter || stageFilter) && (
          <Button size="1" variant="ghost" onClick={() => { setRuleFilter(""); setSeverityFilter(""); setStageFilter(""); setPage(1); }}>
            Clear
          </Button>
        )}
        {issues && (
          <Text size="2" className="ml-auto" style={{ color: "var(--gray-9)" }}>
            {issues.total.toLocaleString()} issues
          </Text>
        )}
      </div>

      {/* Issues table */}
      {issues && (
        <>
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
            <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
              <thead>
                <tr style={{ background: "var(--gray-2)" }}>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>RT ID</th>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Rule</th>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Sev</th>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Field</th>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Value</th>
                  <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Origin</th>
                  <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {issues.results.map((issue) => (
                  <tr key={issue.id}>
                    <td colSpan={7} className="p-0">
                      {/* Row */}
                      <div
                        className="flex items-center px-4 py-2 border-b cursor-pointer hover:bg-[var(--gray-a2)]"
                        style={{
                          borderColor: "var(--gray-4)",
                          borderLeft: issue.status === "flagged" ? "4px solid var(--red-9)" : "4px solid transparent",
                          backgroundColor: issue.status === "flagged" ? "var(--red-2)" : "",
                        }}
                        onClick={() => setExpandedId(expandedId === issue.id ? null : issue.id)}
                      >
                        <span className="font-mono text-[13px] w-24 flex-shrink-0" style={{ color: "var(--accent-11)" }}>
                          {issue.source_id}
                        </span>
                        {issue.status === "flagged" && (
                          <Badge size="1" color="red" variant="solid" className="mr-2">FLAGGED</Badge>
                        )}
                        <span className="w-40 flex-shrink-0">
                          <Badge size="1" variant="soft">{issue.rule.replace(/_/g, " ")}</Badge>
                        </span>
                        <span className="w-16 flex-shrink-0">
                          <Badge size="1" color={SEVERITY_COLORS[issue.severity]} variant="solid">{issue.severity}</Badge>
                        </span>
                        <span className="w-48 flex-shrink-0 font-mono text-[12px] truncate" style={{ color: "var(--gray-11)" }}>
                          {issue.field_path}
                        </span>
                        <span className="flex-1 truncate text-[13px]" style={{ color: "var(--gray-11)" }}>
                          {issue.actual_value?.slice(0, 40) || "—"}
                        </span>
                        <span className="w-24 flex-shrink-0">
                          {issue.introduced_at && (
                            <Badge size="1" variant="outline">{issue.introduced_at}</Badge>
                          )}
                        </span>
                        <span className="w-20 flex-shrink-0 text-right">
                          <Button size="1" variant="ghost" onClick={(e: any) => { e.stopPropagation(); navigate(`/pipeline/trace/${issue.source_id}`); }}>
                            Trace
                          </Button>
                        </span>
                      </div>

                      {/* Expanded detail */}
                      {expandedId === issue.id && (
                        <div className="px-4 py-3 border-b" style={{ borderColor: "var(--gray-4)", background: "var(--gray-1)" }}>
                          <div className="flex flex-col gap-2 text-[13px]">
                            <div>
                              <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>Message</Text>
                              <Text size="2" className="block">{issue.message}</Text>
                            </div>
                            {issue.explanation && (
                              <div>
                                <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>Trace Explanation</Text>
                                <Text size="2" className="block">{issue.explanation}</Text>
                              </div>
                            )}
                            {issue.code_location && (
                              <div>
                                <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>Code to Fix</Text>
                                <Text size="2" className="block font-mono" style={{ color: "var(--accent-11)" }}>{issue.code_location}</Text>
                              </div>
                            )}
                            {issue.actual_value && (
                              <div>
                                <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>Full Value</Text>
                                <pre className="text-[12px] mt-1 p-2 rounded border overflow-auto" style={{ background: "white", borderColor: "var(--gray-4)" }}>
                                  {issue.actual_value}
                                </pre>
                              </div>
                            )}
                            <div className="mt-3 p-3 rounded border" style={{ borderColor: "var(--gray-4)", background: "white" }}>
                              <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Notes (describe what's wrong and what should happen)</Text>
                              <textarea
                                value={flagNotes[issue.id] || ""}
                                onChange={(e) => setFlagNotes({ ...flagNotes, [issue.id]: e.target.value })}
                                placeholder="e.g. 'This company name should be in parties, not address. Classifier Layer 4 fallback is putting it in the wrong field.'"
                                className="w-full h-16 p-2 text-[13px] rounded border resize-none"
                                style={{ borderColor: "var(--gray-5)" }}
                              />
                              <div className="flex gap-2 mt-2">
                                <Button size="1" color="red" onClick={() => handleFlag(issue.id)} disabled={issue.status === "flagged"}>
                                  {issue.status === "flagged" ? "Flagged" : "Flag for Review"}
                                </Button>
                                <Button size="1" color="green" variant="soft" onClick={() => handleStatusChange(issue.id, "resolved")}>Resolve</Button>
                                <Button size="1" variant="soft" onClick={() => handleStatusChange(issue.id, "ignored")}>Ignore</Button>
                                <Button size="1" color="amber" variant="soft" onClick={() => handleStatusChange(issue.id, "false_positive")}>False Positive</Button>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between">
            <Text size="2" style={{ color: "var(--gray-9)" }}>Page {issues.page} of {issues.pages}</Text>
            <div className="flex gap-2">
              <Button size="1" variant="soft" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button size="1" variant="soft" disabled={page >= issues.pages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
