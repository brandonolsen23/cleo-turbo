import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button, Heading, Text } from "@radix-ui/themes";
import { Star, Warning } from "@phosphor-icons/react";
import { fetchApi, mutateApi } from "../api/client";
import type { UserStar, CrmEntityType } from "../types";
import { formatDate } from "../lib/utils";

const TYPE_LABEL: Record<CrmEntityType, string> = {
  contact: "Contact",
  property: "Property",
  group: "Group",
};

const TYPE_PATH: Record<CrmEntityType, string> = {
  contact: "/contacts",
  property: "/properties",
  group: "/groups",
};

type Filter = "all" | CrmEntityType;

export default function QueuePage() {
  const [stars, setStars] = useState<UserStar[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const load = () => {
    fetchApi<UserStar[]>("/stars").then(setStars);
  };

  useEffect(() => {
    load();
    const handler = () => load();
    window.addEventListener("crm-star-changed", handler);
    return () => window.removeEventListener("crm-star-changed", handler);
  }, []);

  if (stars === null) {
    return (
      <div className="p-6">
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  const filtered = filter === "all" ? stars : stars.filter((s) => s.entity_type === filter);

  async function handleUnstar(s: UserStar) {
    await mutateApi(`/stars/${s.entity_type}/${encodeURIComponent(s.entity_id)}`, "DELETE");
    window.dispatchEvent(
      new CustomEvent("crm-star-changed", {
        detail: { entity_type: s.entity_type, entity_id: s.entity_id },
      })
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-4">
        <Heading size="6">Queue</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Your personal to-touch list. Star any contact, property, or group to add it.
          Items auto-clear when you log an activity that references them.
        </Text>
      </div>

      <div className="flex gap-2 mb-4">
        {(["all", "contact", "property", "group"] as Filter[]).map((f) => (
          <Button
            key={f}
            size="2"
            variant={filter === f ? "solid" : "soft"}
            onClick={() => setFilter(f)}
          >
            {f === "all" ? `All (${stars.length})` : TYPE_LABEL[f]}
          </Button>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="border border-[var(--gray-6)] rounded-[var(--card-radius)] p-8 text-center">
          <Text size="3" style={{ color: "var(--gray-9)" }}>
            Nothing in your queue. Hit the ⭐ on any contact, property, or group to add it here.
          </Text>
        </div>
      )}

      <div className="flex flex-col gap-2">
        {filtered.map((s) => (
          <Link
            key={`${s.entity_type}:${s.entity_id}`}
            to={`${TYPE_PATH[s.entity_type]}/${s.entity_id}`}
            className="block p-4 rounded-[var(--card-radius)] border border-[var(--gray-6)] hover:bg-[var(--gray-2)] transition-colors no-underline"
          >
            <div className="flex justify-between items-start gap-3">
              <div className="flex items-start gap-2 flex-1">
                <Star size={18} weight="fill" style={{ color: "var(--accent-11)", marginTop: 2 }} />
                <div className="flex flex-col gap-1 flex-1">
                  <Text size="3" weight="medium">{s.name ?? s.entity_id}</Text>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    {TYPE_LABEL[s.entity_type]}
                    {s.detail ? ` · ${s.detail}` : ""}
                    {` · Starred ${formatDate(s.starred_at)}`}
                  </Text>
                  {s.team_activity && (
                    <div className="flex items-center gap-1 mt-1">
                      <Warning size={14} style={{ color: "var(--amber-11)" }} />
                      <Text size="1" style={{ color: "var(--amber-11)" }}>
                        {s.team_activity.by_user_name} engaged {formatDate(s.team_activity.happened_at)} —{" "}
                        {s.team_activity.activity_type}
                        {s.team_activity.outcome ? ` → ${s.team_activity.outcome}` : ""}
                      </Text>
                    </div>
                  )}
                </div>
              </div>
              <Button
                size="1"
                variant="soft"
                color="gray"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleUnstar(s);
                }}
              >
                Remove
              </Button>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
