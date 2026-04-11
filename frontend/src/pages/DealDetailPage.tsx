import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge, TextField, TextArea } from "@radix-ui/themes";
import { Trash, FloppyDisk } from "@phosphor-icons/react";
import { fetchApi, mutateApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import { DEAL_STAGES, dealStageLabel, DEAL_STAGE_COLORS } from "../lib/theme";
import type { CrmDealDetail, AuditLogEntry, BrowseResponse } from "../types";

export default function DealDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [deal, setDeal] = useState<CrmDealDetail | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    name: "", stage: "", amount: "", close_date: "", description: "",
    next_step: "", priority: "", deal_owner: "", lost_reason: "",
  });
  const [audit, setAudit] = useState<AuditLogEntry[]>([]);
  const [saving, setSaving] = useState(false);

  const load = () => {
    if (!id) return;
    fetchApi<CrmDealDetail>(`/deals/${id}`).then((d) => {
      setDeal(d);
      setForm({
        name: d.name || "",
        stage: d.stage || "long_shot",
        amount: d.amount ? String(d.amount) : "",
        close_date: d.close_date || "",
        description: d.description || "",
        next_step: d.next_step || "",
        priority: d.priority || "",
        deal_owner: d.deal_owner || "",
        lost_reason: d.lost_reason || "",
      });
    });
    fetchApi<{ results: AuditLogEntry[] }>(`/audit/entity/deal/${id}`).then((r) => setAudit(r.results));
  };

  useEffect(load, [id]);

  const handleSave = async () => {
    if (!id) return;
    setSaving(true);
    await mutateApi(`/deals/${id}`, "PATCH", {
      name: form.name || undefined,
      stage: form.stage || undefined,
      amount: form.amount ? parseInt(form.amount) : undefined,
      close_date: form.close_date || undefined,
      description: form.description || undefined,
      next_step: form.next_step || undefined,
      priority: form.priority || undefined,
      deal_owner: form.deal_owner || undefined,
      lost_reason: form.lost_reason || undefined,
    });
    setSaving(false);
    setEditing(false);
    load();
  };

  const handleDelete = async () => {
    if (!id || !confirm("Delete this deal? This cannot be undone.")) return;
    await mutateApi(`/deals/${id}`, "DELETE");
    navigate("/deals");
  };

  if (!deal) return <Text>Loading...</Text>;

  const stageColor = (DEAL_STAGE_COLORS[deal.stage] || "gray") as any;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <Link to="/deals" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
          &larr; Deals
        </Link>
        <div className="flex items-center gap-3 mt-2">
          <Heading size="5" weight="medium">{deal.name}</Heading>
          <Badge size="2" color={stageColor} variant="soft">{dealStageLabel(deal.stage)}</Badge>
          <div className="ml-auto flex gap-2">
            {editing ? (
              <>
                <Button size="2" variant="soft" onClick={() => setEditing(false)}>Cancel</Button>
                <Button size="2" onClick={handleSave} disabled={saving}>
                  <FloppyDisk size={14} />
                  Save
                </Button>
              </>
            ) : (
              <>
                <Button size="2" variant="outline" onClick={() => setEditing(true)}>Edit</Button>
                <Button size="2" variant="outline" color="red" onClick={handleDelete}>
                  <Trash size={14} />
                  Delete
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Left column — details */}
        <div className="col-span-2 flex flex-col gap-4">
          {/* Key metrics */}
          <div className="grid grid-cols-3 gap-4">
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
              <Text size="1" style={{ color: "var(--gray-9)" }}>Amount</Text>
              <Text size="5" weight="bold" className="block mt-1">
                {deal.amount ? formatCurrency(deal.amount) : "—"}
              </Text>
            </div>
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
              <Text size="1" style={{ color: "var(--gray-9)" }}>Close Date</Text>
              <Text size="5" weight="bold" className="block mt-1">
                {deal.close_date ? formatDate(deal.close_date) : "—"}
              </Text>
            </div>
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
              <Text size="1" style={{ color: "var(--gray-9)" }}>Owner</Text>
              <Text size="5" weight="bold" className="block mt-1">
                {deal.deal_owner || "—"}
              </Text>
            </div>
          </div>

          {/* Edit form / read-only details */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="3" weight="medium" className="mb-4 block">Deal Details</Text>
            {editing ? (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Name</Text>
                  <TextField.Root value={form.name} onChange={(e: any) => setForm({ ...form, name: e.target.value })} size="2" />
                </div>
                <div>
                  <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Stage</Text>
                  <select
                    value={form.stage}
                    onChange={(e) => setForm({ ...form, stage: e.target.value })}
                    className="w-full h-9 px-2 text-[14px] rounded border border-[var(--gray-6)] bg-white"
                  >
                    {DEAL_STAGES.map((s) => (
                      <option key={s} value={s}>{dealStageLabel(s)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Amount</Text>
                  <TextField.Root type="number" value={form.amount} onChange={(e: any) => setForm({ ...form, amount: e.target.value })} size="2" />
                </div>
                <div>
                  <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Close Date</Text>
                  <TextField.Root type="date" value={form.close_date} onChange={(e: any) => setForm({ ...form, close_date: e.target.value })} size="2" />
                </div>
                <div>
                  <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Deal Owner</Text>
                  <TextField.Root value={form.deal_owner} onChange={(e: any) => setForm({ ...form, deal_owner: e.target.value })} size="2" />
                </div>
                <div>
                  <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Priority</Text>
                  <select
                    value={form.priority}
                    onChange={(e) => setForm({ ...form, priority: e.target.value })}
                    className="w-full h-9 px-2 text-[14px] rounded border border-[var(--gray-6)] bg-white"
                  >
                    <option value="">None</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
                <div className="col-span-2">
                  <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Description</Text>
                  <TextArea value={form.description} onChange={(e: any) => setForm({ ...form, description: e.target.value })} size="2" rows={3} />
                </div>
                <div className="col-span-2">
                  <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Next Step</Text>
                  <TextField.Root value={form.next_step} onChange={(e: any) => setForm({ ...form, next_step: e.target.value })} size="2" />
                </div>
                {form.stage === "lost" && (
                  <div className="col-span-2">
                    <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Lost Reason</Text>
                    <TextArea value={form.lost_reason} onChange={(e: any) => setForm({ ...form, lost_reason: e.target.value })} size="2" rows={2} />
                  </div>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4 text-[14px]">
                {deal.description && (
                  <div className="col-span-2">
                    <Text size="1" style={{ color: "var(--gray-9)" }}>Description</Text>
                    <Text className="block mt-1">{deal.description}</Text>
                  </div>
                )}
                {deal.next_step && (
                  <div className="col-span-2">
                    <Text size="1" style={{ color: "var(--gray-9)" }}>Next Step</Text>
                    <Text className="block mt-1">{deal.next_step}</Text>
                  </div>
                )}
                {deal.priority && (
                  <div>
                    <Text size="1" style={{ color: "var(--gray-9)" }}>Priority</Text>
                    <Badge size="1" variant="soft" color={deal.priority === "high" ? "red" : deal.priority === "medium" ? "amber" : "gray"} className="mt-1">
                      {deal.priority}
                    </Badge>
                  </div>
                )}
                {deal.lost_reason && (
                  <div className="col-span-2">
                    <Text size="1" style={{ color: "var(--gray-9)" }}>Lost Reason</Text>
                    <Text className="block mt-1">{deal.lost_reason}</Text>
                  </div>
                )}
                <div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>Created</Text>
                  <Text className="block mt-1">{formatDate(deal.created_at)}</Text>
                </div>
                <div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>Updated</Text>
                  <Text className="block mt-1">{formatDate(deal.updated_at)}</Text>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right column — associations + activity */}
        <div className="flex flex-col gap-4">
          {/* Linked Property */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="2" weight="medium" className="mb-3 block">Property</Text>
            {deal.property_id && deal.property_address ? (
              <Link to={`/properties/${deal.property_id}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
                <Text size="2">{deal.property_address}</Text>
                {deal.property_city && (
                  <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>{deal.property_city}</Text>
                )}
              </Link>
            ) : (
              <Text size="2" style={{ color: "var(--gray-9)" }}>No property linked</Text>
            )}
          </div>

          {/* Linked Group */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="2" weight="medium" className="mb-3 block">Group</Text>
            {deal.group_id && deal.group_name ? (
              <Link to={`/groups/${deal.group_id}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
                <Text size="2">{deal.group_name}</Text>
              </Link>
            ) : (
              <Text size="2" style={{ color: "var(--gray-9)" }}>No group linked</Text>
            )}
          </div>

          {/* Activity / Audit Log */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="2" weight="medium" className="mb-3 block">Activity</Text>
            {audit.length === 0 ? (
              <Text size="2" style={{ color: "var(--gray-9)" }}>No activity recorded</Text>
            ) : (
              <div className="flex flex-col gap-2">
                {audit.slice(0, 20).map((a) => (
                  <div key={a.id} className="flex flex-col py-1.5 border-b border-[var(--gray-4)] last:border-0">
                    <div className="flex items-center gap-2">
                      <Badge size="1" variant="soft" color={a.action.includes("create") ? "jade" : a.action.includes("delete") ? "red" : "blue"}>
                        {a.action.split(".")[1] || a.action}
                      </Badge>
                      <Text size="1" style={{ color: "var(--gray-9)" }}>{a.display_name || a.username || "System"}</Text>
                    </div>
                    <Text size="1" style={{ color: "var(--gray-8)" }}>{formatDate(a.created_at)}</Text>
                    {a.details && a.action.includes("update") && (
                      <Text size="1" style={{ color: "var(--gray-9)" }} className="mt-0.5">
                        Changed: {Object.keys(a.details).join(", ")}
                      </Text>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
