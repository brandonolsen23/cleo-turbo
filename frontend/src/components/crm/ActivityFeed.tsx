/**
 * ActivityFeed — displays a chronological list of activities for an entity.
 * Used on SellOpportunityDetail, BuyMandateDetail, and eventually Contact/Group detail pages.
 */
import { useState } from "react";
import { Heading, Text, Badge, Button } from "@radix-ui/themes";
import {
  Phone,
  EnvelopeSimple,
  UsersThree,
  NoteBlank,
  Plus,
} from "@phosphor-icons/react";
import type { Activity, ActivityType, ActivityEntityType } from "../../types";
import { activityTypeColor, activityTypeLabel } from "../../lib/theme";
import { formatDate } from "../../lib/utils";
import LogActivityDialog from "./LogActivityDialog";

const ACTIVITY_ICONS: Record<string, React.ElementType> = {
  call: Phone,
  email: EnvelopeSimple,
  meeting: UsersThree,
  note: NoteBlank,
};

interface ActivityFeedProps {
  activities: Activity[];
  entityType: ActivityEntityType;
  entityId: string;
  onActivityLogged?: () => void;
}

export default function ActivityFeed({
  activities,
  entityType,
  entityId,
  onActivityLogged,
}: ActivityFeedProps) {
  const [showLogDialog, setShowLogDialog] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <Heading size="3">Activity</Heading>
        <Button
          size="1"
          variant="soft"
          onClick={() => setShowLogDialog(true)}
        >
          <Plus size={14} weight="bold" />
          Log Activity
        </Button>
      </div>

      {activities.length === 0 ? (
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          No activities logged yet.
        </Text>
      ) : (
        <div className="space-y-3">
          {activities.map((a) => {
            const Icon = ACTIVITY_ICONS[a.activity_type] || NoteBlank;
            return (
              <div
                key={a.id}
                className="flex gap-3 items-start"
              >
                <div
                  className="mt-0.5 flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center"
                  style={{ backgroundColor: `var(--${activityTypeColor(a.activity_type)}-3)` }}
                >
                  <Icon
                    size={14}
                    weight="bold"
                    style={{ color: `var(--${activityTypeColor(a.activity_type)}-11)` }}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge
                      size="1"
                      color={activityTypeColor(a.activity_type)}
                      variant="soft"
                    >
                      {activityTypeLabel(a.activity_type)}
                    </Badge>
                    {a.outcome && (
                      <Text size="1" style={{ color: "var(--gray-9)" }}>
                        {a.outcome.replace(/_/g, " ")}
                      </Text>
                    )}
                    <Text size="1" style={{ color: "var(--gray-9)" }}>
                      {formatDate(a.created_at)}
                    </Text>
                    {a.created_by && (
                      <Text size="1" style={{ color: "var(--gray-9)" }}>
                        by {a.created_by}
                      </Text>
                    )}
                  </div>
                  {a.summary && (
                    <Text size="2" className="mt-1 block" style={{ color: "var(--gray-12)" }}>
                      {a.summary}
                    </Text>
                  )}
                  {a.next_step && (
                    <Text size="1" className="mt-1 block" style={{ color: "var(--accent-11)" }}>
                      Next: {a.next_step}
                    </Text>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showLogDialog && (
        <LogActivityDialog
          entityType={entityType}
          entityId={entityId}
          onClose={() => setShowLogDialog(false)}
          onSaved={() => {
            setShowLogDialog(false);
            onActivityLogged?.();
          }}
        />
      )}
    </div>
  );
}
