import { useEffect, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge, Callout, TextArea, TextField, Select } from "@radix-ui/themes";
import { CheckCircle, WarningCircle, ClipboardText } from "@phosphor-icons/react";
import { fetchApi, mutateApi } from "../api/client";
import { formatDate } from "../lib/utils";
import type { Issue, IssueStatus, IssueSeverity, IssueCategory } from "../types";

const SEVERITY_COLOR: Record<IssueSeverity, "red" | "orange" | "amber" | "gray"> = {
  critical: "red", high: "orange", medium: "amber", low: "gray",
};

const STATUS_COLOR: Record<IssueStatus, "amber" | "blue" | "jade" | "gray"> = {
  open: "amber", in_progress: "blue", resolved: "jade", wontfix: "gray", duplicate: "gray",
};

const CATEGORY_LABELS: Record<IssueCategory, string> = {
  rt_property_mismatch:   "RT↔Property mismatch",
  parcel_geometry_wrong:  "Parcel geometry wrong",
  wrong_owner:            "Wrong owner",
  group_clustering_issue: "Group clustering",
  parsing_error:          "Parsing error",
  missing_data:           "Missing data",
  duplicate_entity:       "Duplicate entity",
  formatting_issue:       "Formatting",
  layout_issue:           "Layout",
  wrong_calculation:      "Wrong calculation",
  other:                  "Other",
};

const STATUS_OPTIONS: IssueStatus[] = ["open", "in_progress", "resolved", "wontfix", "duplicate"];

function entityHref(it: Issue): string | null {
  if (!it.entity_id) return null;
  switch (it.entity_type) {
    case "property":    return `/properties/${it.entity_id}`;
    case "contact":     return `/contacts/${it.entity_id}`;
    case "group":
    case "auto_group":  return `/groups/${it.entity_id}`;
    case "transaction": return `/transactions/${it.entity_id}`;
    default:            return null;
  }
}

function buildClaudePrompt(it: Issue): string {
  const entity = it.entity_id ? `${it.entity_type} ${it.entity_id}` : it.entity_type;
  const cats = it.categories.map((c) => CATEGORY_LABELS[c]).join(", ");
  const compLine = it.component ? `\nComponent: \`${it.component}\`` : "";
  const dataLine = it.component_data
    ? `\nComponent data: \`${JSON.stringify(it.component_data)}\``
    : "";
  return `Please resolve Issue #${it.id} from the in-app tracker.

Title: ${it.title}
Entity: ${entity}${compLine}${dataLine}
Categories: ${cats}
Severity: ${it.severity}

Description:
${it.description}

Investigate, propose a fix, apply it, and commit. When done, mark the issue resolved with:

\`\`\`
python -m cleo.cli.issues resolve ${it.id} --note "<what you did>" --commit <sha>
\`\`\`

If you decide it's a duplicate or working-as-intended, use:
\`\`\`
python -m cleo.cli.issues close ${it.id} --status duplicate --note "<reason>"
\`\`\`
`;
}

export default function IssueDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [issue, setIssue] = useState<Issue | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Status editor state
  const [status, setStatus] = useState<IssueStatus>("open");
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [commitSha, setCommitSha] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState<string | null>(null);
  const [copyToast, setCopyToast] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchApi<Issue>(`/issues/${id}`)
      .then((d) => {
        setIssue(d);
        setStatus(d.status);
        setResolutionNotes(d.resolution_notes || "");
        setCommitSha(d.fixed_in_commit || "");
      })
      .catch((e) => setError(e?.message || "Failed to load issue"));
  }, [id]);

  const save = async () => {
    if (!issue) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = { status };
      if (resolutionNotes.trim()) body.resolution_notes = resolutionNotes.trim();
      if (commitSha.trim()) body.fixed_in_commit = commitSha.trim();
      const updated = await mutateApi<Issue>(`/issues/${issue.id}`, "PATCH", body);
      setIssue(updated);
      setSavedToast("Saved.");
      setTimeout(() => setSavedToast(null), 2500);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to save.";
      setSavedToast(msg);
    } finally {
      setSaving(false);
    }
  };

  const copyClaudePrompt = async () => {
    if (!issue) return;
    try {
      await navigator.clipboard.writeText(buildClaudePrompt(issue));
      setCopyToast("Claude prompt copied — paste into a fresh chat.");
      setTimeout(() => setCopyToast(null), 3000);
    } catch {
      setCopyToast("Copy failed. Browser may not allow clipboard access.");
    }
  };

  if (error) return (
    <Callout.Root color="red"><Callout.Text>{error}</Callout.Text></Callout.Root>
  );
  if (!issue) return <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>;

  const ent = entityHref(issue);

  return (
    <div className="flex flex-col gap-5">
      <Link to="/issues" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
        ← Issues
      </Link>

      {/* Header */}
      <div className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <Text size="1" style={{ color: "var(--gray-9)" }}>Issue #{issue.id}</Text>
            <Heading size="5" weight="medium" className="mt-1">{issue.title}</Heading>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <Badge size="2" variant={issue.status === "open" ? "solid" : "soft"} color={STATUS_COLOR[issue.status]}>
                {issue.status.replace("_", " ")}
              </Badge>
              <Badge size="2" variant="soft" color={SEVERITY_COLOR[issue.severity]}>{issue.severity}</Badge>
              {issue.categories.map((c) => (
                <Badge key={c} size="1" variant="soft" color="gray">{CATEGORY_LABELS[c]}</Badge>
              ))}
            </div>
          </div>
          <Button onClick={copyClaudePrompt} variant="soft">
            <ClipboardText size={14} className="mr-1" /> Copy Claude prompt
          </Button>
        </div>
        {copyToast && (
          <Callout.Root color="jade">
            <Callout.Icon><CheckCircle size={16} /></Callout.Icon>
            <Callout.Text>{copyToast}</Callout.Text>
          </Callout.Root>
        )}
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* Left: context */}
        <div className="col-span-1 flex flex-col gap-4">
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
            <Text size="1" style={{ color: "var(--gray-9)" }}>Entity</Text>
            <div className="mt-1">
              {ent ? (
                <Link to={ent} className="no-underline" style={{ color: "var(--accent-11)" }}>
                  {issue.entity_type}:{issue.entity_id}
                </Link>
              ) : (
                <Text size="2" style={{ color: "var(--gray-11)" }}>{issue.entity_type}</Text>
              )}
            </div>
            {issue.component && (
              <>
                <Text size="1" className="block mt-3" style={{ color: "var(--gray-9)" }}>Component</Text>
                <code className="text-[12px]" style={{ color: "var(--gray-12)" }}>{issue.component}</code>
              </>
            )}
            {issue.component_data && Object.keys(issue.component_data).length > 0 && (
              <>
                <Text size="1" className="block mt-3" style={{ color: "var(--gray-9)" }}>Component data</Text>
                <pre className="text-[11px] whitespace-pre-wrap p-2 rounded bg-[var(--gray-2)] mt-1"
                     style={{ color: "var(--gray-12)" }}>
                  {JSON.stringify(issue.component_data, null, 2)}
                </pre>
              </>
            )}
            <Text size="1" className="block mt-3" style={{ color: "var(--gray-9)" }}>Reported</Text>
            <Text size="2" style={{ color: "var(--gray-11)" }}>
              {formatDate(issue.reported_at)} by {issue.reported_by}
            </Text>
            {issue.resolved_at && (
              <>
                <Text size="1" className="block mt-3" style={{ color: "var(--gray-9)" }}>Resolved</Text>
                <Text size="2" style={{ color: "var(--gray-11)" }}>
                  {formatDate(issue.resolved_at)} by {issue.resolved_by}
                </Text>
              </>
            )}
            {issue.fixed_in_commit && (
              <>
                <Text size="1" className="block mt-3" style={{ color: "var(--gray-9)" }}>Commit</Text>
                <code className="text-[12px]" style={{ color: "var(--gray-12)" }}>{issue.fixed_in_commit}</code>
              </>
            )}
          </div>
        </div>

        {/* Right: description + resolution */}
        <div className="col-span-2 flex flex-col gap-4">
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
            <Text size="2" weight="medium" style={{ color: "var(--gray-12)" }}>Description</Text>
            <Text as="p" size="2" className="mt-2 whitespace-pre-wrap" style={{ color: "var(--gray-11)" }}>
              {issue.description}
            </Text>
          </div>

          {/* Status editor */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
            <Text size="2" weight="medium" style={{ color: "var(--gray-12)" }}>Update</Text>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Status</Text>
                <Select.Root value={status} onValueChange={(v) => setStatus(v as IssueStatus)}>
                  <Select.Trigger className="mt-1 w-full" />
                  <Select.Content>
                    {STATUS_OPTIONS.map((s) => (
                      <Select.Item key={s} value={s}>{s.replace("_", " ")}</Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </div>
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Commit (optional)</Text>
                <TextField.Root
                  className="mt-1"
                  value={commitSha}
                  onChange={(e) => setCommitSha(e.target.value)}
                  placeholder="git sha"
                />
              </div>
            </div>
            <div className="mt-3">
              <Text size="1" style={{ color: "var(--gray-9)" }}>Resolution notes</Text>
              <TextArea
                className="mt-1"
                rows={4}
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                placeholder="What was done to resolve this issue?"
              />
            </div>
            <div className="mt-3 flex items-center justify-between">
              {savedToast ? (
                <Text size="1" style={{ color: savedToast === "Saved." ? "var(--jade-11)" : "var(--red-11)" }}>
                  {savedToast === "Saved." && <CheckCircle size={12} className="inline mr-1" />}
                  {savedToast !== "Saved." && <WarningCircle size={12} className="inline mr-1" />}
                  {savedToast}
                </Text>
              ) : <span />}
              <Button onClick={save} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
