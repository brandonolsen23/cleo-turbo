import { useEffect, useState } from "react";
import { Dialog, Text, Button, Badge, TextField, Callout } from "@radix-ui/themes";
import { PencilSimple, Sparkle, CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../../api/client";
import { formatCanonicalAddress } from "../../lib/utils";

interface Props {
  autoGroupId: string;
  currentAddress: string | null;
  currentSource: string | null;
  onUpdated: () => void;
}

interface Candidate {
  address: string;
  party_side_count: number;
  first_seen: string;
  last_seen: string;
  is_current: boolean;
}

interface CandidatesResponse {
  current: { primary_address: string | null; primary_address_source: string | null };
  candidates: Candidate[];
}

interface EnrichProposal {
  primary_address: string | null;
  primary_address_canonical: string | null;
  website: string | null;
  primary_phone: string | null;
  evidence_snippets: string[];
  confidence: number;
  reasoning: string;
  _source_pages?: string[];
}

export default function HqPicker({ autoGroupId, currentAddress, currentSource, onUpdated }: Props) {
  const [open, setOpen] = useState(false);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [proposal, setProposal] = useState<EnrichProposal | null>(null);
  const [enriching, setEnriching] = useState(false);
  const [accept, setAccept] = useState({ address: true, website: true, phone: true });

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setStatus(null);
    setProposal(null);
    fetchApi<CandidatesResponse>(`/auto-groups/${autoGroupId}/address-candidates`)
      .then((r) => setCandidates(r.candidates))
      .catch((e) => setStatus({ type: "error", message: String(e) }))
      .finally(() => setLoading(false));
  }, [open, autoGroupId]);

  const pickCandidate = async (addr: string) => {
    setStatus(null);
    try {
      await postApi(`/auto-groups/${autoGroupId}/set-address`, { primary_address: addr });
      setStatus({ type: "success", message: "HQ updated." });
      onUpdated();
      setTimeout(() => setOpen(false), 400);
    } catch (e: any) {
      setStatus({ type: "error", message: e?.message || String(e) });
    }
  };

  const runEnrich = async () => {
    if (!websiteUrl.trim()) return;
    setEnriching(true);
    setStatus(null);
    setProposal(null);
    try {
      const r = await postApi<{ proposal: EnrichProposal }>(
        `/auto-groups/${autoGroupId}/enrich`,
        { website_url: websiteUrl.trim() },
      );
      setProposal(r.proposal);
    } catch (e: any) {
      setStatus({ type: "error", message: e?.message || "Enrichment failed" });
    } finally {
      setEnriching(false);
    }
  };

  const acceptProposal = async () => {
    if (!proposal) return;
    setStatus(null);
    const body: Record<string, string | null> = {};
    if (accept.address) body.primary_address = proposal.primary_address_canonical || proposal.primary_address || null;
    if (accept.website) body.website = proposal.website;
    if (accept.phone) body.primary_phone = proposal.primary_phone;
    if (Object.keys(body).length === 0) {
      setStatus({ type: "error", message: "Select at least one field to apply." });
      return;
    }
    try {
      await postApi(`/auto-groups/${autoGroupId}/accept-enrichment`, body);
      setStatus({ type: "success", message: "AI proposal applied." });
      onUpdated();
      setTimeout(() => setOpen(false), 400);
    } catch (e: any) {
      setStatus({ type: "error", message: e?.message || "Accept failed" });
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 text-[12px] hover:underline"
        style={{ color: "var(--accent-11)" }}
        aria-label="Edit HQ address"
      >
        <PencilSimple size={12} /> Edit
      </button>

      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Content maxWidth="600px">
          <Dialog.Title>HQ address</Dialog.Title>
          <Dialog.Description size="2" mb="4">
            Pick from the most-frequent recent addresses, or enrich via AI by pasting the company's website URL.
          </Dialog.Description>

          {status && (
            <Callout.Root color={status.type === "success" ? "jade" : "red"} size="1" mb="3">
              <Callout.Icon>
                {status.type === "success" ? <CheckCircle size={14} /> : <WarningCircle size={14} />}
              </Callout.Icon>
              <Callout.Text>{status.message}</Callout.Text>
            </Callout.Root>
          )}

          <div className="flex flex-col gap-3">
            <Text size="2" weight="medium">Candidates from this group's transactions</Text>
            {loading && <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>}
            {candidates && candidates.length === 0 && (
              <Text size="2" style={{ color: "var(--gray-9)" }}>No address candidates yet.</Text>
            )}
            {candidates && candidates.map((c) => (
              <button
                key={c.address}
                onClick={() => pickCandidate(c.address)}
                className="text-left rounded-md border p-3 hover:bg-[var(--gray-2)] transition-colors"
                style={{ borderColor: c.is_current ? "var(--accent-7)" : "var(--gray-6)" }}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[14px]">{formatCanonicalAddress(c.address)}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {c.is_current && <Badge size="1" color="jade" variant="soft">current</Badge>}
                    <Text size="1" style={{ color: "var(--gray-9)" }}>
                      {c.party_side_count} parties · last {c.last_seen?.slice(0, 10)}
                    </Text>
                  </div>
                </div>
              </button>
            ))}

            {/* AI enrichment */}
            <div className="mt-2 rounded-md border border-[var(--gray-6)] p-3">
              <div className="flex items-center gap-2 mb-2">
                <Sparkle size={14} weight="fill" style={{ color: "var(--amber-9)" }} />
                <Text size="2" weight="medium">Use AI to verify HQ</Text>
              </div>
              <Text size="1" style={{ color: "var(--gray-9)" }} mb="2">
                Paste the company's website. Claude will read the homepage and Contact page and propose an HQ + phone.
              </Text>
              <div className="flex gap-2 mt-2">
                <TextField.Root
                  size="1"
                  placeholder="https://example.com"
                  value={websiteUrl}
                  onChange={(e: any) => setWebsiteUrl(e.target.value)}
                  style={{ flex: 1 }}
                />
                <Button size="1" onClick={runEnrich} disabled={enriching || !websiteUrl.trim()}>
                  {enriching ? "Searching…" : "Find HQ"}
                </Button>
              </div>

              {proposal && (
                <div className="mt-3 flex flex-col gap-2 text-[13px]">
                  {proposal.primary_address && (
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={accept.address}
                        onChange={(e) => setAccept({ ...accept, address: e.target.checked })}
                        className="mt-1"
                      />
                      <div>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>Address</Text>
                        <Text size="2" className="block">{proposal.primary_address}</Text>
                      </div>
                    </label>
                  )}
                  {proposal.website && (
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={accept.website}
                        onChange={(e) => setAccept({ ...accept, website: e.target.checked })}
                        className="mt-1"
                      />
                      <div>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>Website</Text>
                        <Text size="2" className="block">{proposal.website}</Text>
                      </div>
                    </label>
                  )}
                  {proposal.primary_phone && (
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={accept.phone}
                        onChange={(e) => setAccept({ ...accept, phone: e.target.checked })}
                        className="mt-1"
                      />
                      <div>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>HQ phone</Text>
                        <Text size="2" className="block">{proposal.primary_phone}</Text>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>
                          Used as a verification anchor only; shown on the Group card, not on individual contacts.
                        </Text>
                      </div>
                    </label>
                  )}
                  {proposal.reasoning && (
                    <Text size="1" style={{ color: "var(--gray-11)" }}>
                      {proposal.reasoning} (confidence: {Math.round((proposal.confidence ?? 0) * 100)}%)
                    </Text>
                  )}
                  {proposal.evidence_snippets && proposal.evidence_snippets.length > 0 && (
                    <div className="rounded bg-[var(--gray-2)] p-2">
                      <Text size="1" weight="medium" style={{ color: "var(--gray-11)" }}>Evidence</Text>
                      <ul className="text-[12px] mt-1 ml-3 list-disc" style={{ color: "var(--gray-11)" }}>
                        {proposal.evidence_snippets.map((s, i) => (
                          <li key={i}>"{s}"</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div className="flex justify-end">
                    <Button size="1" onClick={acceptProposal}>Apply selected</Button>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-end mt-4">
            <Dialog.Close>
              <Button variant="soft">Close</Button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Root>
    </>
  );
}
