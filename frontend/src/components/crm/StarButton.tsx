import { useEffect, useState, useCallback } from "react";
import { Star } from "@phosphor-icons/react";
import { fetchApi, postApi, mutateApi } from "../../api/client";
import type { CrmEntityType } from "../../types";

interface StarButtonProps {
  entityType: CrmEntityType;
  entityId: string;
  size?: number;
  showLabel?: boolean;
  className?: string;
}

const EVENT_NAME = "crm-star-changed";

export default function StarButton({
  entityType,
  entityId,
  size = 18,
  showLabel = false,
  className,
}: StarButtonProps) {
  const [starred, setStarred] = useState<boolean | null>(null);
  const [pending, setPending] = useState(false);

  const refresh = useCallback(() => {
    fetchApi<{ starred: boolean }>(
      `/stars/check?entity_type=${entityType}&entity_id=${encodeURIComponent(entityId)}`
    )
      .then((r) => setStarred(r.starred))
      .catch(() => setStarred(false));
  }, [entityType, entityId]);

  useEffect(() => {
    refresh();
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ entity_type: string; entity_id: string }>).detail;
      if (detail.entity_type === entityType && detail.entity_id === entityId) refresh();
    };
    window.addEventListener(EVENT_NAME, handler as EventListener);
    return () => window.removeEventListener(EVENT_NAME, handler as EventListener);
  }, [refresh, entityType, entityId]);

  async function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (pending || starred === null) return;
    const next = !starred;
    setStarred(next); // optimistic
    setPending(true);
    try {
      if (next) {
        await postApi("/stars", { entity_type: entityType, entity_id: entityId });
      } else {
        await mutateApi(`/stars/${entityType}/${encodeURIComponent(entityId)}`, "DELETE");
      }
      window.dispatchEvent(
        new CustomEvent(EVENT_NAME, { detail: { entity_type: entityType, entity_id: entityId } })
      );
    } catch {
      setStarred(!next); // revert
    } finally {
      setPending(false);
    }
  }

  const label = showLabel ? (starred ? "Starred" : "Star") : null;
  const color = starred ? "var(--accent-11)" : "var(--gray-9)";

  return (
    <button
      onClick={toggle}
      disabled={pending || starred === null}
      title={starred ? "Remove from queue" : "Add to queue"}
      className={
        className ??
        "inline-flex items-center gap-1 px-2 py-1 rounded text-[13px] hover:bg-[var(--gray-3)] transition-colors disabled:opacity-50"
      }
      style={{ color }}
    >
      <Star size={size} weight={starred ? "fill" : "regular"} />
      {label && <span>{label}</span>}
    </button>
  );
}
