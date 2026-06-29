/**
 * Issue Reporter — global modal + provider + Reportable wrapper.
 *
 * Three pieces work together:
 *   1. <IssueReporterProvider> at the app root holds modal state.
 *   2. <Reportable component="..." data={...}> wraps any UI element. On hover
 *      it reveals a small `i` button in the top-right corner. Clicking opens
 *      the modal pre-filled with that component's identity.
 *   3. Global Cmd+Shift+B opens the modal scoped to the current page (no
 *      component context). Page entity is derived from the URL.
 *
 * Categories are user-friendly multi-select chips. Severity is auto-derived
 * server-side from the highest-severity category and never shown at report
 * time (per the plan — reduces field count to title / categories / notes).
 */

import {
  createContext, useContext, useState, useEffect, useCallback,
  type ReactNode,
} from "react";
import { useLocation, useParams } from "react-router-dom";
import { Dialog, Button, TextField, TextArea, Text, Badge, Callout } from "@radix-ui/themes";
import { Info, CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { postApi } from "../../api/client";
import type {
  IssueCategory, IssueEntityType, IssueReportContext, Issue,
} from "../../types";

// ── Categories ─────────────────────────────────────────────────────────

interface CategoryDef {
  value: IssueCategory;
  label: string;
  description: string;
}

const CATEGORIES: CategoryDef[] = [
  { value: "rt_property_mismatch",   label: "RT ↔ Property mismatch",
    description: "Transaction linked to the wrong parcel" },
  { value: "parcel_geometry_wrong",  label: "Parcel geometry wrong",
    description: "Map outline / photos from a different site" },
  { value: "wrong_owner",            label: "Wrong owner",
    description: "Current owner is incorrect" },
  { value: "group_clustering_issue", label: "Group clustering",
    description: "Auto-group includes / excludes wrong SPVs" },
  { value: "parsing_error",          label: "Parsing error",
    description: "Field has a wrong-type value (address as contact, etc.)" },
  { value: "missing_data",           label: "Missing data",
    description: "Expected field is empty when source has it" },
  { value: "duplicate_entity",       label: "Duplicate entity",
    description: "Same record exists twice" },
  { value: "formatting_issue",       label: "Formatting / display",
    description: "Pipes in HQ, raw values, bad date format" },
  { value: "layout_issue",           label: "Layout / overflow",
    description: "Table overflowing, card squished, etc." },
  { value: "wrong_calculation",      label: "Wrong calculation",
    description: "Counts / sums don't reconcile" },
  { value: "other",                  label: "Other / feature request",
    description: "Catch-all" },
];

// ── URL → entity context ───────────────────────────────────────────────

/** Derive (entity_type, entity_id) from the current React-Router URL.
 *  Returns 'general' / null when no entity is identifiable. */
function deriveEntityFromUrl(pathname: string): {
  entity_type: IssueEntityType; entity_id: string | null; contextLabel: string;
} {
  // /properties/PRO_xxxxx
  const m1 = pathname.match(/^\/properties\/([^/]+)/);
  if (m1) return { entity_type: "property", entity_id: m1[1], contextLabel: `Property ${m1[1]}` };
  // /contacts/CON_xxxxx
  const m2 = pathname.match(/^\/contacts\/([^/]+)/);
  if (m2) return { entity_type: "contact", entity_id: m2[1], contextLabel: `Contact ${m2[1]}` };
  // /groups/{AGRP_xxxxx | GRP_xxxxx}
  const m3 = pathname.match(/^\/groups\/([^/]+)/);
  if (m3) {
    const isAuto = m3[1].startsWith("AGRP_");
    return {
      entity_type: isAuto ? "auto_group" : "group",
      entity_id: m3[1],
      contextLabel: `Group ${m3[1]}`,
    };
  }
  // /transactions/RT_xxxxx
  const m4 = pathname.match(/^\/transactions\/([^/]+)/);
  if (m4) return { entity_type: "transaction", entity_id: m4[1], contextLabel: `Transaction ${m4[1]}` };
  return { entity_type: "general", entity_id: null, contextLabel: pathname };
}

// ── Context ────────────────────────────────────────────────────────────

interface IssueReporterAPI {
  open: (ctx?: Partial<IssueReportContext>) => void;
}

const IssueReporterCtx = createContext<IssueReporterAPI | null>(null);

export function useIssueReporter(): IssueReporterAPI {
  const ctx = useContext(IssueReporterCtx);
  if (!ctx) {
    // No-op fallback when used outside the provider
    return { open: () => console.warn("useIssueReporter outside provider") };
  }
  return ctx;
}

// ── Provider + modal ───────────────────────────────────────────────────

export function IssueReporterProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [overrideCtx, setOverrideCtx] = useState<Partial<IssueReportContext> | null>(null);

  // Form state
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [selectedCats, setSelectedCats] = useState<Set<IssueCategory>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string; id?: number } | null>(null);

  const openModal = useCallback((ctx?: Partial<IssueReportContext>) => {
    setOverrideCtx(ctx || null);
    setTitle("");
    setNotes("");
    setSelectedCats(new Set());
    setStatus(null);
    setOpen(true);
  }, []);

  const api: IssueReporterAPI = { open: openModal };

  // Cmd+Shift+B global shortcut → page-level report
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === "b" || e.key === "B")) {
        e.preventDefault();
        openModal();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openModal]);

  // Compose the effective context for THIS open: override (from Reportable
  // click) takes precedence; otherwise fall back to page-derived.
  const derived = deriveEntityFromUrl(location.pathname);
  const effective: IssueReportContext = {
    entity_type: overrideCtx?.entity_type ?? derived.entity_type,
    entity_id:   overrideCtx?.entity_id   ?? derived.entity_id,
    component:   overrideCtx?.component,
    component_data: overrideCtx?.component_data,
    contextLabel: overrideCtx?.contextLabel ?? derived.contextLabel,
  };

  const toggleCat = (c: IssueCategory) => {
    setSelectedCats((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c); else next.add(c);
      return next;
    });
  };

  const submit = async () => {
    if (!title.trim() || !notes.trim() || selectedCats.size === 0) {
      setStatus({ type: "error", message: "Title, at least one category, and notes are required." });
      return;
    }
    setSubmitting(true);
    setStatus(null);
    try {
      const issue = await postApi<Issue>("/issues", {
        entity_type:   effective.entity_type,
        entity_id:     effective.entity_id ?? null,
        component:     effective.component ?? null,
        component_data: effective.component_data ?? null,
        categories:    Array.from(selectedCats),
        title:         title.trim(),
        description:   notes.trim(),
      });
      setStatus({ type: "success", message: `Filed as Issue #${issue.id}.`, id: issue.id });
      setTitle(""); setNotes(""); setSelectedCats(new Set());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to file the issue.";
      setStatus({ type: "error", message: msg });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <IssueReporterCtx.Provider value={api}>
      {children}
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Content style={{ maxWidth: 560 }}>
          <Dialog.Title>Report an issue</Dialog.Title>

          {/* Context strip — what you're reporting on */}
          <div className="mt-2 mb-3 rounded-md bg-[var(--gray-2)] p-2 px-3">
            <Text size="1" style={{ color: "var(--gray-9)" }}>Reporting:</Text>{" "}
            <Text size="2" style={{ color: "var(--gray-12)" }}>
              {effective.contextLabel}
              {effective.component && (
                <> · <code style={{ fontSize: 12, color: "var(--gray-11)" }}>{effective.component}</code></>
              )}
            </Text>
            {effective.component_data && Object.keys(effective.component_data).length > 0 && (
              <div className="mt-1">
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  data: <code style={{ fontSize: 11, color: "var(--gray-11)" }}>
                    {JSON.stringify(effective.component_data)}
                  </code>
                </Text>
              </div>
            )}
          </div>

          {/* Title */}
          <div className="mb-3">
            <Text size="2" weight="medium" style={{ color: "var(--gray-12)" }}>Title</Text>
            <TextField.Root
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="One-line summary"
              size="2"
              className="mt-1"
            />
          </div>

          {/* Categories — multi-select chips */}
          <div className="mb-3">
            <Text size="2" weight="medium" style={{ color: "var(--gray-12)" }}>
              Categories <span style={{ color: "var(--gray-9)", fontWeight: "normal" }}>(pick one or more)</span>
            </Text>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {CATEGORIES.map((c) => {
                const on = selectedCats.has(c.value);
                return (
                  <button
                    key={c.value}
                    type="button"
                    onClick={() => toggleCat(c.value)}
                    title={c.description}
                    className="px-2.5 py-1 text-[12px] rounded-md border transition-colors"
                    style={{
                      background: on ? "var(--accent-3)" : "white",
                      borderColor: on ? "var(--accent-7)" : "var(--gray-6)",
                      color: on ? "var(--accent-11)" : "var(--gray-11)",
                      fontWeight: on ? 500 : 400,
                    }}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Notes */}
          <div className="mb-3">
            <Text size="2" weight="medium" style={{ color: "var(--gray-12)" }}>Notes</Text>
            <TextArea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="What did you see? What should it be? Paste any related IDs / URLs / details that would help Claude resolve this."
              rows={6}
              size="2"
              className="mt-1"
            />
          </div>

          {status && (
            <Callout.Root color={status.type === "success" ? "jade" : "red"} className="mb-3">
              <Callout.Icon>
                {status.type === "success" ? <CheckCircle size={16} /> : <WarningCircle size={16} />}
              </Callout.Icon>
              <Callout.Text>{status.message}</Callout.Text>
            </Callout.Root>
          )}

          <div className="flex justify-between items-center gap-2">
            <Text size="1" style={{ color: "var(--gray-9)" }}>
              Cmd+Shift+B opens this from anywhere
            </Text>
            <div className="flex gap-2">
              <Dialog.Close>
                <Button variant="soft" color="gray">Close</Button>
              </Dialog.Close>
              <Button
                onClick={submit}
                disabled={submitting || !title.trim() || !notes.trim() || selectedCats.size === 0}
              >
                {submitting ? "Filing…" : status?.type === "success" ? "File another" : "File issue"}
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Root>
    </IssueReporterCtx.Provider>
  );
}

// ── <Reportable> wrapper ───────────────────────────────────────────────

interface ReportableProps {
  component: string;
  data?: Record<string, unknown>;
  /** Override entity if the wrapped component spans a different entity than
   *  what the URL would suggest (rare — most components match the page). */
  entity_type?: IssueEntityType;
  entity_id?: string | null;
  contextLabel?: string;
  children: ReactNode;
  /** When set, render inline so the `i` button doesn't disrupt the layout
   *  (useful inside table rows). Default is "block" — relative-positioned
   *  wrapper with the icon absolutely placed top-right. */
  inline?: boolean;
}

export function Reportable({
  component, data, entity_type, entity_id, contextLabel, children, inline,
}: ReportableProps) {
  const { open } = useIssueReporter();
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    open({ component, component_data: data, entity_type, entity_id, contextLabel });
  };

  if (inline) {
    return (
      <span className="inline-flex items-center gap-1 group/reportable">
        {children}
        <button
          type="button"
          onClick={handleClick}
          className="opacity-0 group-hover/reportable:opacity-100 transition-opacity"
          title="Report issue with this row"
          style={{ color: "var(--gray-9)" }}
        >
          <Info size={13} weight="bold" />
        </button>
      </span>
    );
  }

  return (
    <div className="relative group/reportable">
      {children}
      <button
        type="button"
        onClick={handleClick}
        className="absolute top-2 right-2 opacity-0 group-hover/reportable:opacity-100 transition-opacity rounded-full bg-white border border-[var(--gray-6)] p-1 shadow-sm hover:border-[var(--accent-7)] hover:text-[var(--accent-11)]"
        title="Report issue with this component"
        style={{ color: "var(--gray-9)", zIndex: 10 }}
      >
        <Info size={12} weight="bold" />
      </button>
    </div>
  );
}
