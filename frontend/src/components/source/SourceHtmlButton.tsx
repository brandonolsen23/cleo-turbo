import { FileHtml } from "@phosphor-icons/react";
import { useSourceViewer } from "./SourceViewerContext";

interface SourceHtmlButtonProps {
  sourceId: string;
  size?: number;
}

/**
 * Small icon button that opens the source HTML drawer for a transaction.
 * Only render this when has_source_html is true.
 */
export default function SourceHtmlButton({ sourceId, size = 16 }: SourceHtmlButtonProps) {
  const { openSource } = useSourceViewer();

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        openSource(sourceId);
      }}
      className="inline-flex items-center justify-center p-0.5 rounded hover:bg-[var(--gray-3)] transition-colors cursor-pointer"
      style={{ color: "var(--gray-9)", border: "none", background: "none" }}
      title="View source HTML"
    >
      <FileHtml size={size} />
    </button>
  );
}
