import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge } from "@radix-ui/themes";
import { Copy, MagnifyingGlass } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatDate } from "../lib/utils";
import JsonTree from "../components/pipeline/JsonTree";

interface RecordResponse {
  stage: string;
  filename: string;
  file_size: number;
  modified_at: string;
  data: Record<string, unknown>;
}

const STAGE_LABELS: Record<string, string> = {
  assembled: "Assembled", classified: "Classified", addresses: "Addresses",
  parcel_links: "Parcel Links", clean: "Clean Records",
};

export default function PipelineRecordPage() {
  const { stage, "*": filename } = useParams();
  const navigate = useNavigate();
  const [record, setRecord] = useState<RecordResponse | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (stage && filename) {
      fetchApi<RecordResponse>(`/pipeline/record/${stage}/${filename}`).then(setRecord);
    }
  }, [stage, filename]);

  if (!record) return <Text>Loading...</Text>;

  // Extract RT ID from filename
  const rtIdMatch = record.filename.match(/^(RT\d+)/);
  const rtId = rtIdMatch?.[1];

  const copyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(record.data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const fileSizeStr = record.file_size > 1024
    ? `${(record.file_size / 1024).toFixed(1)} KB`
    : `${record.file_size} bytes`;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex items-center gap-1 text-[14px]">
          <Link to="/pipeline" className="no-underline" style={{ color: "var(--accent-11)" }}>Pipeline</Link>
          <span style={{ color: "var(--gray-8)" }}>/</span>
          <Link to={`/pipeline/${stage}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
            {STAGE_LABELS[stage || ""] || stage}
          </Link>
        </div>
        <Heading size="5" weight="medium" className="mt-2 font-mono">{record.filename}</Heading>
      </div>

      {/* Metadata + actions */}
      <div className="flex items-center gap-4">
        <Badge size="1" variant="soft">{STAGE_LABELS[stage || ""] || stage}</Badge>
        <Text size="1" style={{ color: "var(--gray-9)" }}>{fileSizeStr}</Text>
        <Text size="1" style={{ color: "var(--gray-9)" }}>Modified: {formatDate(record.modified_at)}</Text>
        <div className="ml-auto flex gap-2">
          <Button size="1" variant="soft" onClick={copyJson}>
            <Copy size={14} />
            {copied ? "Copied!" : "Copy JSON"}
          </Button>
          {rtId && (
            <Button size="1" variant="outline" onClick={() => navigate(`/pipeline/trace/${rtId}`)}>
              <MagnifyingGlass size={14} />
              Trace {rtId}
            </Button>
          )}
        </div>
      </div>

      {/* JSON tree */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4 overflow-hidden">
        <JsonTree data={record.data} defaultExpand={3} />
      </div>
    </div>
  );
}
