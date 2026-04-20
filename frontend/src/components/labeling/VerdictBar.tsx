import { useEffect } from "react";
import { Button, TextField, Badge } from "@radix-ui/themes";
import { CheckCircle, XCircle, SkipForward, Trash, Sparkle } from "@phosphor-icons/react";
import type { LinkKind, FieldType } from "../../types";
import type { PendingLink } from "./proposals";

interface Props {
  linkKind: LinkKind;
  setLinkKind: (k: LinkKind) => void;
  rationale: string;
  setRationale: (s: string) => void;
  disabled: boolean;
  pendingLinks: PendingLink[];
  setPendingLinks: (l: PendingLink[]) => void;
  onConfirm: () => void;
  onReject: () => void;
  onSkip: () => void;
}

export default function VerdictBar({
  linkKind, setLinkKind, rationale, setRationale, disabled,
  pendingLinks, setPendingLinks, onConfirm, onReject, onSkip,
}: Props) {
  // Click-to-link: capture clicks on elements with data-link-anchor
  useEffect(() => {
    let pendingLeft: { field_type: FieldType; field_value: string } | null = null;

    function handleClick(e: MouseEvent) {
      const target = (e.target as HTMLElement).closest("[data-link-anchor]") as HTMLElement | null;
      if (!target) return;
      const pane = target.dataset.pane as "left" | "right";
      const field_type = target.dataset.fieldType as FieldType;
      const field_value = target.dataset.fieldValue || "";
      if (pane === "left") {
        pendingLeft = { field_type, field_value };
      } else if (pane === "right" && pendingLeft) {
        // Dedup identical links
        const already = pendingLinks.find(
          (l) => l.from_field_type === pendingLeft!.field_type
              && l.from_field_value === pendingLeft!.field_value
              && l.to_field_type === field_type
              && l.to_field_value === field_value,
        );
        if (!already) {
          setPendingLinks([...pendingLinks, {
            from_field_type: pendingLeft.field_type,
            from_field_value: pendingLeft.field_value,
            to_field_type: field_type,
            to_field_value: field_value,
            kind: linkKind,
          }]);
        }
        pendingLeft = null;
      }
    }

    function handleKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return; // don't intercept while typing
      // Shift+A clears auto-proposed links (keeps anything manually drawn)
      if (e.shiftKey && e.key.toLowerCase() === "a") {
        setPendingLinks(pendingLinks.filter((l) => !l.auto));
        return;
      }
      if (e.key.toLowerCase() === "e") setLinkKind("exact");
      else if (e.key.toLowerCase() === "i") setLinkKind("implied");
      else if (!disabled && e.key.toLowerCase() === "c") onConfirm();
      else if (!disabled && e.key.toLowerCase() === "r") onReject();
      else if (!disabled && e.key.toLowerCase() === "s") onSkip();
    }

    document.addEventListener("click", handleClick, true);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("click", handleClick, true);
      document.removeEventListener("keydown", handleKey);
    };
  }, [linkKind, pendingLinks, setPendingLinks, setLinkKind, disabled, onConfirm, onReject, onSkip]);

  return (
    <div className="border-t border-[var(--gray-4)] p-3 flex flex-col gap-2"
         style={{ background: "var(--gray-2)" }}>
      <div className="flex items-center gap-3">
        <span className="text-[12px]" style={{ color: "var(--gray-9)" }}>Mode (E / I):</span>
        <Button size="1" variant={linkKind === "exact" ? "solid" : "soft"} onClick={() => setLinkKind("exact")}>
          ● Exact
        </Button>
        <Button size="1" variant={linkKind === "implied" ? "solid" : "soft"} onClick={() => setLinkKind("implied")}>
          ○ Implied
        </Button>
        <div className="flex-1" />
        <TextField.Root size="1" placeholder="Rationale (required for reject)"
                        value={rationale}
                        onChange={(e) => setRationale(e.target.value)}
                        style={{ width: 320 }} />
        <Button size="1" color="jade" disabled={disabled || pendingLinks.length === 0} onClick={onConfirm}>
          <CheckCircle size={12} /> Confirm (C)
        </Button>
        <Button size="1" color="tomato" variant="soft"
                disabled={disabled || !rationale.trim()} onClick={onReject}>
          <XCircle size={12} /> Reject (R)
        </Button>
        <Button size="1" variant="soft" disabled={disabled} onClick={onSkip}>
          <SkipForward size={12} /> Skip (S)
        </Button>
      </div>
      {pendingLinks.length > 0 && (
        <div className="flex flex-wrap gap-1 items-center">
          {pendingLinks.some((l) => l.auto) && (
            <span className="text-[11px] flex items-center gap-1"
                  style={{ color: "var(--gray-9)" }}>
              <Sparkle size={10} /> auto — review &amp; remove any wrong ones · Shift+A to clear
            </span>
          )}
          {pendingLinks.map((l, i) => (
            <Badge key={i} size="1"
                   variant={l.auto ? "outline" : "soft"}
                   color={l.kind === "exact" ? "jade" : "blue"}>
              {l.auto && <Sparkle size={10} weight={l.auto === "learned" ? "fill" : "regular"} />}
              {l.from_field_type}:{l.from_field_value}
              {" → "}
              {l.to_field_type}:{l.to_field_value}
              {l.auto && <span style={{ marginLeft: 4, opacity: 0.7 }}>· {l.auto}</span>}
              <button className="ml-1 opacity-70 hover:opacity-100"
                      onClick={() => setPendingLinks(pendingLinks.filter((_, j) => j !== i))}>
                <Trash size={10} />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
