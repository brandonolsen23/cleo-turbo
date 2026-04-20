import { useEffect, useRef, useState } from "react";
import type { LabelingLinkInput } from "../../types";

interface Props {
  links: LabelingLinkInput[];
}

interface Segment {
  x1: number; y1: number; x2: number; y2: number;
  kind: "exact" | "implied";
  key: string;
}

function findAnchor(pane: "left" | "right", field_type: string, value: string): DOMRect | null {
  const el = document.querySelector(
    `[data-link-anchor="1"][data-pane="${pane}"][data-field-type="${field_type}"][data-field-value="${cssEscape(value)}"]`
  ) as HTMLElement | null;
  return el?.getBoundingClientRect() ?? null;
}

function cssEscape(s: string): string {
  // Attribute-value selector needs quote-safe content; rely on CSS.escape if available
  return (typeof CSS !== "undefined" && (CSS as any).escape) ? (CSS as any).escape(s) : s.replace(/"/g, '\\"');
}

export default function LinkCanvas({ links }: Props) {
  const [segments, setSegments] = useState<Segment[]>([]);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    function recompute() {
      const segs: Segment[] = [];
      for (let i = 0; i < links.length; i++) {
        const l = links[i];
        const a = findAnchor("left", l.from_field_type, l.from_field_value);
        const b = findAnchor("right", l.to_field_type, l.to_field_value);
        if (a && b) {
          segs.push({
            x1: a.left + a.width / 2, y1: a.top + a.height / 2,
            x2: b.left + b.width / 2, y2: b.top + b.height / 2,
            kind: l.kind,
            key: `${i}:${l.from_field_type}:${l.from_field_value}->${l.to_field_type}:${l.to_field_value}`,
          });
        }
      }
      setSegments(segs);
    }
    function schedule() {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(recompute);
    }
    recompute();
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    return () => {
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      cancelAnimationFrame(rafRef.current);
    };
  }, [links]);

  return (
    <svg
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 50,
      }}
      width="100%"
      height="100%"
    >
      {segments.map((s) => (
        <line
          key={s.key}
          x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
          stroke="var(--accent-9)"
          strokeWidth={2}
          strokeDasharray={s.kind === "implied" ? "5 4" : undefined}
        />
      ))}
    </svg>
  );
}
