import { createContext, useContext, useState, useCallback } from "react";

export interface CrmEntity {
  type: "contact" | "group" | "property" | "deal";
  id: string;
  name: string;
}

interface CrmContextType {
  isOpen: boolean;
  entity: CrmEntity | null;
  openDrawer: (entity: CrmEntity) => void;
  closeDrawer: () => void;
  refreshKey: number;
  triggerRefresh: () => void;
}

const CrmCtx = createContext<CrmContextType>({
  isOpen: false,
  entity: null,
  openDrawer: () => {},
  closeDrawer: () => {},
  refreshKey: 0,
  triggerRefresh: () => {},
});

export function useCrm() {
  return useContext(CrmCtx);
}

export function CrmProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [entity, setEntity] = useState<CrmEntity | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const openDrawer = useCallback((e: CrmEntity) => {
    setEntity(e);
    setIsOpen(true);
  }, []);

  const closeDrawer = useCallback(() => {
    setIsOpen(false);
  }, []);

  const triggerRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

  return (
    <CrmCtx.Provider value={{ isOpen, entity, openDrawer, closeDrawer, refreshKey, triggerRefresh }}>
      {children}
    </CrmCtx.Provider>
  );
}
