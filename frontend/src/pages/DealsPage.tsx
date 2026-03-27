import { useState, useEffect } from "react";
import { Heading, Text, Button, Badge, TextField, TextArea } from "@radix-ui/themes";
import { Plus, X } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import { DEAL_STAGES, dealStageLabel, DEAL_STAGE_COLORS } from "../lib/theme";

interface DealItem {
  id: string;
  name: string;
  stage: string;
  amount: number | null;
  close_date: string | null;
  deal_owner: string | null;
  property_id: string | null;
  group_id: string | null;
  description: string | null;
}

interface PipelineData {
  stages: { stage: string; deals: DealItem[] }[];
  stats: { total: number; active: number; pipeline_value: number };
}

export default function DealsPage() {
  const [pipeline, setPipeline] = useState<PipelineData | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", stage: "long_shot", amount: "", close_date: "", description: "" });

  const load = () => {
    fetchApi<PipelineData>("/deals/pipeline").then(setPipeline);
  };

  useEffect(load, []);

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    await postApi("/deals", {
      name: form.name,
      stage: form.stage,
      amount: form.amount ? parseInt(form.amount) : null,
      close_date: form.close_date || null,
      description: form.description || null,
    });
    setForm({ name: "", stage: "long_shot", amount: "", close_date: "", description: "" });
    setShowForm(false);
    load();
  };

  if (!pipeline) return <Text>Loading...</Text>;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Deals</Heading>
        <Button size="2" onClick={() => setShowForm(true)}>
          <Plus size={14} />
          New Deal
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="2" style={{ color: "var(--gray-9)" }}>Total Deals</Text>
          <Heading size="5" weight="medium" className="mt-1">{pipeline.stats.total}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="2" style={{ color: "var(--gray-9)" }}>Active</Text>
          <Heading size="5" weight="medium" className="mt-1">{pipeline.stats.active}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="2" style={{ color: "var(--gray-9)" }}>Pipeline Value</Text>
          <Heading size="5" weight="medium" className="mt-1">{formatCurrency(pipeline.stats.pipeline_value)}</Heading>
        </div>
      </div>

      {/* Pipeline board */}
      <div className="flex gap-3 overflow-x-auto pb-4" style={{ minHeight: 300 }}>
        {pipeline.stages.map((s) => {
          const color = (DEAL_STAGE_COLORS[s.stage] || "gray") as any;
          return (
            <div
              key={s.stage}
              className="flex flex-col rounded-lg border"
              style={{ minWidth: 200, width: 200, borderColor: "var(--gray-4)", background: "var(--gray-2)" }}
            >
              {/* Stage header */}
              <div className="flex items-center justify-between px-3 py-2 border-b" style={{ borderColor: "var(--gray-4)" }}>
                <Badge size="1" color={color} variant="soft">{dealStageLabel(s.stage)}</Badge>
                <Text size="1" style={{ color: "var(--gray-9)" }}>{s.deals.length}</Text>
              </div>

              {/* Deal cards */}
              <div className="flex flex-col gap-2 p-2 flex-1 overflow-y-auto">
                {s.deals.length === 0 ? (
                  <div className="flex items-center justify-center h-16">
                    <Text size="1" style={{ color: "var(--gray-8)" }}>No deals</Text>
                  </div>
                ) : (
                  s.deals.map((d) => (
                    <div
                      key={d.id}
                      className="rounded-lg border bg-white p-3 cursor-pointer hover:border-[var(--gray-6)] transition-colors"
                      style={{ borderColor: "var(--gray-4)" }}
                    >
                      <Text size="2" weight="medium" className="block">{d.name}</Text>
                      {d.amount && (
                        <Text size="2" className="block mt-1" style={{ color: "var(--gray-11)" }}>
                          {formatCurrency(d.amount)}
                        </Text>
                      )}
                      {d.close_date && (
                        <Text size="1" className="block mt-1" style={{ color: "var(--gray-9)" }}>
                          Close: {formatDate(d.close_date)}
                        </Text>
                      )}
                      {d.deal_owner && (
                        <Text size="1" className="block mt-1" style={{ color: "var(--gray-9)" }}>
                          {d.deal_owner}
                        </Text>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* New Deal Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.15)" }}>
          <div className="w-[440px] rounded-[var(--card-radius)] border border-[var(--gray-6)] bg-white p-6" style={{ boxShadow: "var(--elevation-4)" }}>
            <div className="flex items-center justify-between mb-4">
              <Heading size="4" weight="medium">New Deal</Heading>
              <button onClick={() => setShowForm(false)} className="p-1 rounded hover:bg-gray-100">
                <X size={16} />
              </button>
            </div>
            <div className="flex flex-col gap-3">
              <div>
                <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Name</Text>
                <TextField.Root value={form.name} onChange={(e: any) => setForm({ ...form, name: e.target.value })} size="2" placeholder="Deal name" />
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
                <TextField.Root type="number" value={form.amount} onChange={(e: any) => setForm({ ...form, amount: e.target.value })} size="2" placeholder="0" />
              </div>
              <div>
                <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Close Date</Text>
                <TextField.Root type="date" value={form.close_date} onChange={(e: any) => setForm({ ...form, close_date: e.target.value })} size="2" />
              </div>
              <div>
                <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Description</Text>
                <TextArea value={form.description} onChange={(e: any) => setForm({ ...form, description: e.target.value })} size="2" placeholder="Optional" />
              </div>
              <div className="flex justify-end gap-2 mt-2">
                <Button variant="soft" size="2" onClick={() => setShowForm(false)}>Cancel</Button>
                <Button size="2" onClick={handleCreate} disabled={!form.name.trim()}>Create Deal</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
