import { useState } from "react";
import { Button } from "@radix-ui/themes";
import { NotePencil, ListPlus, Briefcase, Tag, Handshake } from "@phosphor-icons/react";
import StarButton from "./StarButton";
import LogActivityDialog from "./LogActivityDialog";
import AddToListDrawer from "./AddToListDrawer";
import CreateDealDrawer from "./CreateDealDrawer";
import type { CrmEntityType } from "../../types";

interface QuickActionBarProps {
  entityType: CrmEntityType;
  entityId: string;
  entityName: string;
  ownerName?: string;
  onCreateSellOpp?: () => void;     // Property only
  onCreateBuyMandate?: () => void;  // Contact + Group only
  onActivityLogged?: () => void;
}

export default function QuickActionBar({
  entityType,
  entityId,
  entityName,
  ownerName,
  onCreateSellOpp,
  onCreateBuyMandate,
  onActivityLogged,
}: QuickActionBarProps) {
  const [showLog, setShowLog] = useState(false);
  const [showAddToList, setShowAddToList] = useState(false);
  const [showCreateDeal, setShowCreateDeal] = useState(false);

  return (
    <>
      <div className="flex items-center gap-2 flex-wrap">
        <StarButton entityType={entityType} entityId={entityId} showLabel />
        <Button size="2" variant="soft" onClick={() => setShowLog(true)}>
          <NotePencil size={14} /> Log activity
        </Button>
        <Button size="2" variant="soft" onClick={() => setShowAddToList(true)}>
          <ListPlus size={14} /> Add to list
        </Button>
        <Button size="2" variant="soft" onClick={() => setShowCreateDeal(true)}>
          <Briefcase size={14} /> Create deal
        </Button>
        {entityType === "property" && onCreateSellOpp && (
          <Button size="2" variant="soft" onClick={onCreateSellOpp}>
            <Tag size={14} /> Sell opportunity
          </Button>
        )}
        {(entityType === "contact" || entityType === "group") && onCreateBuyMandate && (
          <Button size="2" variant="soft" onClick={onCreateBuyMandate}>
            <Handshake size={14} /> Buy mandate
          </Button>
        )}
      </div>

      {showLog && (
        <LogActivityDialog
          entityType={entityType}
          entityId={entityId}
          onClose={() => setShowLog(false)}
          onSaved={() => {
            setShowLog(false);
            onActivityLogged?.();
          }}
        />
      )}
      {showAddToList && (
        <AddToListDrawer
          memberType={entityType}
          memberId={entityId}
          onClose={() => setShowAddToList(false)}
        />
      )}
      {showCreateDeal && (
        <CreateDealDrawer
          entityType={entityType}
          entityId={entityId}
          entityName={entityName}
          ownerName={ownerName}
          onClose={() => setShowCreateDeal(false)}
        />
      )}
    </>
  );
}
