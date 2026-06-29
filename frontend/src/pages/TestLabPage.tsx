import { useEffect, useMemo, useState } from "react";
import { Heading, Text, Badge, Button, TextField } from "@radix-ui/themes";
import { Flask, MagnifyingGlass, Star } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";

type LatticeNode = {
  phrase: string;
  length: number;
  scope_rt_count: number;
  scope_side_count: number;
  total_rt_count: number;
  purity: number;
  leaf_count: number;
};

type Leaf = {
  phrase: string;
  scope_rt_count: number;
  scope_side_count: number;
  source_fields: string[];
  token_count: number;
};

type LatticeResponse = {
  seed: string;
  seed_normalized: string;
  seed_tokens: string[];
  scope_rt_count: number;
  scope_side_count: number;
  leaves: Leaf[];
  ngrams_by_length: Record<string, LatticeNode[]>;
};

type NodeAnchor = { value: string; share_count: number; share_pct: number };
type LeafInNode = { phrase: string; rt_count: number; side_count: number; source_fields: string[] };

type PartyAddress = {
  street: string | null;
  suite: string | null;
  city: string | null;
  province: string | null;
  postal: string | null;
};

type PartyContact = {
  display_name: string | null;
  title: string | null;
  job_title: string | null;
};

type PartyPackage = {
  source_id: string;
  side: string;
  side_label: string;
  sale_date: string | null;
  sale_price: number | null;
  subject_address: string | null;
  subject_city: string | null;
  subject_region: string | null;
  party_names: string[];
  trade_name: string | null;
  care_of: string | null;
  companies: string[];
  law_firms: string[];
  contact: PartyContact | null;
  phones: string[];
  address: PartyAddress | null;
};

type NodeResponse = {
  seed: string;
  phrase: string;
  phrase_normalized: string;
  length: number;
  scope_rt_count: number;
  scope_side_count: number;
  total_rt_count: number;
  purity: number;
  rts: string[];
  leaves: LeafInNode[];
  shared_anchors: {
    addresses: NodeAnchor[];
    contacts: NodeAnchor[];
    phones: NodeAnchor[];
  };
  scope_packages: PartyPackage[];
  scope_packages_total: number;
  leak_packages: PartyPackage[];
  leak_packages_total: number;
};

const QUICK_SEEDS = ["canadian commercial", "dh management"];

function purityBadge(purity: number) {
  if (purity >= 0.95) return <Badge color="jade">{(purity * 100).toFixed(0)}%</Badge>;
  if (purity >= 0.5) return <Badge color="amber">{(purity * 100).toFixed(0)}%</Badge>;
  if (purity >= 0.1) return <Badge color="orange">{(purity * 100).toFixed(0)}%</Badge>;
  return <Badge color="tomato">{(purity * 100).toFixed(1)}%</Badge>;
}

export default function TestLabPage() {
  const [seedInput, setSeedInput] = useState<string>("canadian commercial");
  const [activeSeed, setActiveSeed] = useState<string>("canadian commercial");
  const [lattice, setLattice] = useState<LatticeResponse | null>(null);
  const [latticeErr, setLatticeErr] = useState<string | null>(null);
  const [latticeLoading, setLatticeLoading] = useState<boolean>(false);

  const [selectedPhrase, setSelectedPhrase] = useState<string | null>(null);
  const [nodeDetail, setNodeDetail] = useState<NodeResponse | null>(null);
  const [nodeLoading, setNodeLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!activeSeed) return;
    setLatticeLoading(true);
    setLatticeErr(null);
    setLattice(null);
    setSelectedPhrase(null);
    setNodeDetail(null);
    fetchApi<LatticeResponse>("/test-lab/lattice", { seed: activeSeed })
      .then((data) => {
        setLattice(data);
        // Auto-select the seed phrase itself in the lattice
        setSelectedPhrase(data.seed_normalized);
      })
      .catch((e) => setLatticeErr(String(e)))
      .finally(() => setLatticeLoading(false));
  }, [activeSeed]);

  useEffect(() => {
    if (!activeSeed || !selectedPhrase) return;
    setNodeLoading(true);
    fetchApi<NodeResponse>("/test-lab/node", { seed: activeSeed, phrase: selectedPhrase })
      .then(setNodeDetail)
      .catch(() => setNodeDetail(null))
      .finally(() => setNodeLoading(false));
  }, [activeSeed, selectedPhrase]);

  const lengths = useMemo(() => {
    if (!lattice) return [];
    return Object.keys(lattice.ngrams_by_length).sort((a, b) => Number(a) - Number(b));
  }, [lattice]);

  const submitSeed = () => {
    const trimmed = seedInput.trim();
    if (trimmed) setActiveSeed(trimmed);
  };

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <div className="flex items-center gap-2 mb-2">
        <Flask size={22} weight="duotone" style={{ color: "var(--accent-11)" }} />
        <Heading size="6">Test Lab</Heading>
      </div>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        Walk the n-gram lattice for a seed phrase. Scope is the set of party-sides carrying the seed.
        Each n-gram shows scope-RT / total-RT, with purity = scope / total. The shortest n-gram with
        100% purity is the canonical stem for this family.
      </Text>

      {/* Seed picker */}
      <div className="mt-5 flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <TextField.Root
            value={seedInput}
            onChange={(e) => setSeedInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submitSeed(); }}
            placeholder="seed phrase (e.g., canadian commercial)"
            style={{ width: 320 }}
          >
            <TextField.Slot><MagnifyingGlass size={14} /></TextField.Slot>
          </TextField.Root>
          <Button onClick={submitSeed} variant="solid">Load</Button>
        </div>
        <div className="flex items-center gap-2">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Quick:</Text>
          {QUICK_SEEDS.map((s) => (
            <Button
              key={s}
              size="1"
              variant={activeSeed === s ? "solid" : "soft"}
              onClick={() => { setSeedInput(s); setActiveSeed(s); }}
            >
              {s}
            </Button>
          ))}
        </div>
      </div>

      {latticeErr && <div className="mt-4"><Text color="tomato">{latticeErr}</Text></div>}
      {latticeLoading && <div className="mt-4"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading lattice…</Text></div>}

      {lattice && !latticeLoading && (
        <>
          {/* Scope summary strip */}
          <div className="grid grid-cols-4 gap-4 mt-5">
            <ScopeCard label="Seed (normalized)" value={lattice.seed_normalized} mono />
            <ScopeCard label="Scope — RTs" value={lattice.scope_rt_count.toLocaleString()} />
            <ScopeCard label="Scope — Party Sides" value={lattice.scope_side_count.toLocaleString()} />
            <ScopeCard label="Distinct Brand-Phrase Leaves" value={lattice.leaves.length.toLocaleString()} />
          </div>

          {/* Two-pane: lattice (L) + node detail (R) */}
          <div className="grid grid-cols-[1.4fr_1fr] gap-5 mt-5">
            {/* Lattice */}
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
              <div className="px-4 py-2 bg-[var(--gray-2)] border-b border-[var(--gray-6)] flex items-center justify-between">
                <Heading size="3">Lattice</Heading>
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  click an n-gram to see its in-scope RTs, leaves, and shared anchors
                </Text>
              </div>
              <div className="p-3 max-h-[78vh] overflow-y-auto">
                {lengths.length === 0 && (
                  <Text size="2" style={{ color: "var(--gray-9)" }}>No n-grams in scope.</Text>
                )}
                {lengths.map((len) => (
                  <div key={len} className="mb-4">
                    <div className="flex items-center gap-2 px-1 mb-1">
                      <Badge variant="soft" color="gray">{len}-gram</Badge>
                      <Text size="1" style={{ color: "var(--gray-9)" }}>
                        {lattice.ngrams_by_length[len].length} unique
                      </Text>
                    </div>
                    <div className="flex flex-col gap-px">
                      {lattice.ngrams_by_length[len].map((n) => {
                        const isSelected = selectedPhrase === n.phrase;
                        const isCanonical =
                          n.purity >= 0.95 && n.phrase === lattice.seed_normalized;
                        return (
                          <button
                            key={n.phrase}
                            onClick={() => setSelectedPhrase(n.phrase)}
                            className="flex items-center gap-3 px-2 py-1.5 rounded text-left transition-colors"
                            style={{
                              background: isSelected ? "var(--accent-a3)" : "transparent",
                              border: isSelected ? "1px solid var(--accent-7)" : "1px solid transparent",
                            }}
                          >
                            <div className="flex items-center gap-1.5 min-w-0 flex-1">
                              {isCanonical && (
                                <Star size={12} weight="fill" style={{ color: "var(--jade-11)" }} />
                              )}
                              <span
                                className="font-mono text-[13px] truncate"
                                style={{ color: "var(--gray-12)" }}
                              >
                                {n.phrase}
                              </span>
                            </div>
                            <Text size="1" style={{ color: "var(--gray-9)", fontVariantNumeric: "tabular-nums" }}>
                              {n.scope_rt_count}/{n.total_rt_count}
                            </Text>
                            {purityBadge(n.purity)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Selected node detail */}
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
              <div className="px-4 py-2 bg-[var(--gray-2)] border-b border-[var(--gray-6)]">
                <Heading size="3">Selected n-gram</Heading>
              </div>
              <div className="p-4 max-h-[78vh] overflow-y-auto">
                {!selectedPhrase && (
                  <Text size="2" style={{ color: "var(--gray-9)" }}>Pick an n-gram on the left.</Text>
                )}
                {selectedPhrase && nodeLoading && (
                  <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
                )}
                {selectedPhrase && nodeDetail && (
                  <NodeDetailPane node={nodeDetail} />
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ScopeCard({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
      <Text size="1" style={{ color: "var(--gray-9)" }}>{label}</Text>
      <div className="mt-1">
        <span className={mono ? "font-mono text-[16px]" : "text-[18px] font-medium"} style={{ color: "var(--gray-12)" }}>
          {value}
        </span>
      </div>
    </div>
  );
}

function NodeDetailPane({ node }: { node: NodeResponse }) {
  const [tab, setTab] = useState<"scope" | "leak">("scope");
  const ngramTokens = node.phrase_normalized.toLowerCase().split(/\s+/).filter(Boolean);
  const leakCount = node.leak_packages_total;
  const scopeCount = node.scope_packages_total;

  // Reset tab when node changes
  useEffect(() => { setTab("scope"); }, [node.phrase_normalized]);

  const list = tab === "scope" ? node.scope_packages : node.leak_packages;
  const shown = list.length;
  const total = tab === "scope" ? scopeCount : leakCount;

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div>
        <div className="font-mono text-[15px]" style={{ color: "var(--gray-12)" }}>
          {node.phrase_normalized}
        </div>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <Badge variant="soft" color="gray">{node.length}-gram</Badge>
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            {node.scope_rt_count} in scope / {node.total_rt_count} total RTs
          </Text>
          {purityBadge(node.purity)}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-[var(--gray-6)]">
        <TabButton
          active={tab === "scope"}
          label={`In scope · ${scopeCount}`}
          tone="scope"
          onClick={() => setTab("scope")}
        />
        <TabButton
          active={tab === "leak"}
          label={`Leak · ${leakCount}`}
          tone="leak"
          onClick={() => setTab("leak")}
          disabled={leakCount === 0}
        />
      </div>

      {tab === "leak" && leakCount > 0 && (
        <Text size="1" style={{ color: "var(--orange-11)" }}>
          These Party Sides carry "{node.phrase_normalized}" but are NOT in the seed's family —
          using this n-gram as a Group stem would merge them in.
        </Text>
      )}

      {shown === 0 ? (
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          {tab === "scope" ? "No Party Sides in scope." : "No leak — this n-gram is exclusive to the seed."}
        </Text>
      ) : (
        <div className="flex flex-col gap-2">
          {list.map((p) => (
            <PartyPackageCard
              key={`${p.source_id}-${p.side}`}
              pkg={p}
              ngramTokens={ngramTokens}
              tone={tab}
            />
          ))}
          {shown < total && (
            <Text size="1" style={{ color: "var(--gray-9)" }}>
              Showing {shown} of {total}.
            </Text>
          )}
        </div>
      )}
    </div>
  );
}

function TabButton({
  active, label, tone, onClick, disabled,
}: {
  active: boolean; label: string; tone: "scope" | "leak"; onClick: () => void; disabled?: boolean;
}) {
  const color = tone === "scope" ? "var(--jade-11)" : "var(--orange-11)";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="px-3 py-1.5 text-[13px] transition-colors"
      style={{
        borderBottom: active ? `2px solid ${color}` : "2px solid transparent",
        color: active ? color : "var(--gray-11)",
        fontWeight: active ? 500 : 400,
        marginBottom: "-1px",
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        background: "transparent",
      }}
    >
      {label}
    </button>
  );
}

function PartyPackageCard({
  pkg, ngramTokens, tone,
}: {
  pkg: PartyPackage; ngramTokens: string[]; tone: "scope" | "leak";
}) {
  const borderColor = tone === "leak" ? "var(--orange-6)" : "var(--gray-6)";
  const bgAccent = tone === "leak" ? "var(--orange-2)" : "var(--gray-2)";
  return (
    <div
      className="rounded-[var(--card-radius)] border overflow-hidden text-[13px]"
      style={{ borderColor }}
    >
      {/* Header strip */}
      <div
        className="px-3 py-1.5 border-b flex items-center gap-2 flex-wrap"
        style={{ background: bgAccent, borderColor }}
      >
        <a
          href={`/transactions/${pkg.source_id}`}
          className="font-mono no-underline"
          style={{ color: "var(--accent-11)", fontWeight: 500 }}
        >
          {pkg.source_id}
        </a>
        <Text size="1" style={{ color: "var(--gray-11)" }}>·</Text>
        <Text size="1" style={{ color: "var(--gray-11)" }}>{pkg.sale_date || "—"}</Text>
        {pkg.sale_price !== null && pkg.sale_price > 0 && (
          <>
            <Text size="1" style={{ color: "var(--gray-11)" }}>·</Text>
            <Text size="1" style={{ color: "var(--gray-11)" }}>{formatPrice(pkg.sale_price)}</Text>
          </>
        )}
        <Badge variant="soft" size="1" color={pkg.side === "buyer" ? "blue" : "violet"} ml="2">
          {pkg.side_label}
        </Badge>
      </div>

      {/* Body */}
      <div className="px-3 py-2 flex flex-col gap-1">
        {/* Party names */}
        {pkg.party_names.length > 0 && (
          <div className="flex flex-col gap-0.5">
            {pkg.party_names.map((name, i) => (
              <div key={i} className="flex items-baseline justify-between gap-2">
                <div className="font-medium" style={{ color: "var(--gray-12)" }}>
                  <Highlighted text={name} tokens={ngramTokens} />
                </div>
                {i === 0 && pkg.phones.length > 0 && (
                  <Text size="1" style={{ color: "var(--gray-11)", whiteSpace: "nowrap" }}>
                    {pkg.phones[0]}
                  </Text>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Trade name (italic) */}
        {pkg.trade_name && (
          <div className="italic" style={{ color: "var(--gray-11)" }}>
            <Highlighted text={pkg.trade_name} tokens={ngramTokens} />
          </div>
        )}

        {/* Care of */}
        {pkg.care_of && (
          <div style={{ color: "var(--gray-11)" }}>
            c/o <Highlighted text={pkg.care_of} tokens={ngramTokens} />
          </div>
        )}

        {/* Companies */}
        {pkg.companies.length > 0 && (
          <div className="text-[12px]" style={{ color: "var(--gray-11)" }}>
            {pkg.companies.map((c, i) => (
              <span key={i}>
                {i > 0 && ", "}
                <Highlighted text={c} tokens={ngramTokens} />
              </span>
            ))}
          </div>
        )}

        {/* Law firms (faded) */}
        {pkg.law_firms.length > 0 && (
          <div className="text-[11px]" style={{ color: "var(--gray-9)" }}>
            law: {pkg.law_firms.join(", ")}
          </div>
        )}

        {/* Contact + address */}
        {(pkg.contact || pkg.address) && (
          <div className="mt-1 pt-1.5 border-t border-dashed" style={{ borderColor: "var(--gray-5)" }}>
            {pkg.contact && (pkg.contact.display_name || pkg.contact.title) && (
              <div style={{ color: "var(--gray-12)" }}>
                {pkg.contact.title ? `${pkg.contact.title}: ` : ""}
                {pkg.contact.display_name || "—"}
              </div>
            )}
            {pkg.address && (pkg.address.street || pkg.address.city) && (
              <div className="text-[12px]" style={{ color: "var(--gray-11)" }}>
                {pkg.address.street && <div>{capWords(pkg.address.street)}{pkg.address.suite ? `, ${capWords(pkg.address.suite)}` : ""}</div>}
                <div>
                  {pkg.address.city ? capWords(pkg.address.city) : ""}
                  {pkg.address.city && pkg.address.province ? ", " : ""}
                  {pkg.address.province ? capWords(pkg.address.province) : ""}
                </div>
                {pkg.address.postal && <div>{pkg.address.postal}</div>}
              </div>
            )}
          </div>
        )}

        {/* Subject property (faded footer) */}
        {pkg.subject_address && (
          <div className="mt-1 text-[11px]" style={{ color: "var(--gray-9)" }}>
            Subject: {pkg.subject_address}{pkg.subject_city ? `, ${pkg.subject_city}` : ""}
          </div>
        )}
      </div>
    </div>
  );
}

function Highlighted({ text, tokens }: { text: string; tokens: string[] }) {
  if (!text || tokens.length === 0) return <>{text}</>;
  // Split by word boundaries and highlight tokens (case-insensitive)
  const tokenSet = new Set(tokens.map((t) => t.toLowerCase()));
  const parts = text.split(/(\b)/);
  return (
    <>
      {parts.map((p, i) => {
        const low = p.toLowerCase();
        if (tokenSet.has(low)) {
          return (
            <mark
              key={i}
              style={{ background: "var(--jade-a4)", color: "var(--gray-12)", padding: "0 2px", borderRadius: 2 }}
            >
              {p}
            </mark>
          );
        }
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

function capWords(s: string): string {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatPrice(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}
