import { useMemo } from "react";
import { ReactFlow, Background, Controls, MarkerType, type Node, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Heading, Text, Badge } from "@radix-ui/themes";
import type {
  AutoGroupTrailResponse,
  AutoGroupTrailThread,
} from "../../types";


function partyLabel(p: AutoGroupTrailResponse['party']): string {
  const addr = [p.street_number, p.street_name, p.street_suffix].filter(Boolean).join(" ");
  const lines = [
    p.brand_phrase || `${p.source_id} (${p.side})`,
    p.sale_date ? p.sale_date.slice(0, 10) : null,
    p.sale_price ? `$${(p.sale_price / 1_000_000).toFixed(2)}M` : null,
    addr || null,
    p.contact ? `contact: ${p.contact}` : null,
    p.phone ? `phone: ${p.phone}` : null,
  ].filter(Boolean);
  return lines.join("\n");
}

function threadEdgeColor(thread: AutoGroupTrailThread, primaryGroupId: string | null): string {
  // Conflict: anchor points at >1 group, or points at a group that's NOT primary.
  if (thread.groups.length > 1) return "var(--tomato-9)";
  if (thread.groups.length === 0) return "var(--gray-9)";
  if (primaryGroupId && thread.groups[0].auto_group_id !== primaryGroupId) {
    return "var(--amber-9)";
  }
  return "var(--jade-9)";
}

const tierColor: Record<string, "jade" | "amber" | "gray"> = {
  confirmed: "jade",
  probable: "amber",
  candidate: "gray",
};


export default function AutoGroupTrail({ trail }: { trail: AutoGroupTrailResponse }) {
  const { nodes, edges, hasConflict, hasUnattached } = useMemo(() => {
    const partyId = `party:${trail.party.source_id}:${trail.party.side}`;
    const primaryId = trail.primary_group?.auto_group_id ?? null;

    // Layout: party node on the left at x=0, group nodes stacked on the right at x=600.
    const nodes: Node[] = [{
      id: partyId,
      type: 'default',
      position: { x: 0, y: 0 },
      data: { label: partyLabel(trail.party) },
      style: {
        background: 'var(--gray-2)',
        border: '1px solid var(--gray-6)',
        padding: 10,
        whiteSpace: 'pre-wrap',
        fontSize: 12,
        width: 240,
      },
    }];

    const groupSpacingY = 110;
    const groupCount = trail.all_groups.length;
    const startY = -((groupCount - 1) * groupSpacingY) / 2;
    trail.all_groups.forEach((g, i) => {
      nodes.push({
        id: `group:${g.auto_group_id}`,
        type: 'default',
        position: { x: 600, y: startY + i * groupSpacingY },
        data: {
          label: `${g.display_name}\n[${g.tier}] ${g.canonical_stem}`,
        },
        style: {
          background: g.auto_group_id === primaryId ? 'var(--jade-3)' : 'var(--gray-3)',
          border: `1px solid ${g.auto_group_id === primaryId ? 'var(--jade-9)' : 'var(--gray-6)'}`,
          padding: 10,
          whiteSpace: 'pre-wrap',
          fontSize: 12,
          width: 220,
          fontWeight: g.auto_group_id === primaryId ? 600 : 400,
        },
      });
    });

    // One edge per (thread, group) pair. Color encodes conflict/unattached state.
    const edges: Edge[] = [];
    let unattached = false;
    let conflict = false;

    trail.threads.forEach((thread, threadIdx) => {
      if (thread.groups.length === 0) {
        unattached = true;
        // Add a stub "(unattached)" node + edge so the user can see the dead end.
        const stubId = `unattached:${thread.anchor_type}:${threadIdx}`;
        nodes.push({
          id: stubId,
          type: 'default',
          position: { x: 600, y: startY + (groupCount + threadIdx) * groupSpacingY },
          data: { label: '(no group)' },
          style: {
            background: 'transparent',
            border: '1px dashed var(--gray-9)',
            padding: 6,
            fontSize: 11,
            color: 'var(--gray-9)',
            width: 100,
          },
        });
        edges.push({
          id: `edge:${threadIdx}:unattached`,
          source: partyId,
          target: stubId,
          label: `${thread.anchor_type}: ${thread.anchor_value}`,
          labelStyle: { fontSize: 10, fill: 'var(--gray-11)' },
          style: { stroke: 'var(--gray-9)', strokeDasharray: '4 4' },
          markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--gray-9)' },
        });
        return;
      }
      if (thread.groups.length > 1) conflict = true;
      const color = threadEdgeColor(thread, primaryId);
      thread.groups.forEach((g, gIdx) => {
        edges.push({
          id: `edge:${threadIdx}:${gIdx}`,
          source: partyId,
          target: `group:${g.auto_group_id}`,
          label: `${thread.anchor_type}: ${thread.anchor_value}`,
          labelStyle: { fontSize: 10, fill: color },
          style: { stroke: color, strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color },
        });
      });
    });

    return { nodes, edges, hasConflict: conflict, hasUnattached: unattached };
  }, [trail]);

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <Heading size="3">Evidence trail</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {trail.threads.length} threads, {trail.all_groups.length} groups touched.
        </Text>
        {trail.primary_group && (
          <Badge color={tierColor[trail.primary_group.tier]}>
            primary: {trail.primary_group.display_name}
          </Badge>
        )}
        {hasConflict && (
          <Badge color="tomato">conflict</Badge>
        )}
        {hasUnattached && (
          <Badge color="gray">unattached anchors</Badge>
        )}
      </div>

      <div style={{ width: "100%", height: 480, background: "var(--gray-2)" }}>
        <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false}
                   panOnScroll proOptions={{ hideAttribution: true }}>
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
