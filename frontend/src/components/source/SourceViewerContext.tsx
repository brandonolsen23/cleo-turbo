import { createContext, useContext, useState, useCallback } from "react";

interface SourceViewerContextType {
  isOpen: boolean;
  sourceId: string | null;
  openSource: (sourceId: string) => void;
  closeSource: () => void;
}

const SourceViewerCtx = createContext<SourceViewerContextType>({
  isOpen: false,
  sourceId: null,
  openSource: () => {},
  closeSource: () => {},
});

export function useSourceViewer() {
  return useContext(SourceViewerCtx);
}

export function SourceViewerProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [sourceId, setSourceId] = useState<string | null>(null);

  const openSource = useCallback((id: string) => {
    setSourceId(id);
    setIsOpen(true);
  }, []);

  const closeSource = useCallback(() => {
    setIsOpen(false);
  }, []);

  return (
    <SourceViewerCtx.Provider value={{ isOpen, sourceId, openSource, closeSource }}>
      {children}
    </SourceViewerCtx.Provider>
  );
}
