import { useEffect, useState, useCallback, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge, Button } from "@radix-ui/themes";
import { CaretLeft, DownloadSimple } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../api/client";
import type {
  LabelingSession, LabelingSeed, LabelingCandidate, LabelingPartyView,
  LabelingVerdict, LabelingLink, LinkKind,
} from "../types";

import SeedQueuePanel from "../components/labeling/SeedQueuePanel";
import PartyCard from "../components/labeling/PartyCard";
import CandidateListPanel from "../components/labeling/CandidateListPanel";
import LinkCanvas from "../components/labeling/LinkCanvas";
import VerdictBar from "../components/labeling/VerdictBar";
import {
  type PendingLink, proposeExactLinks, proposeLearnedLinks,
  computeLearnedPairs, stripAuto,
} from "../components/labeling/proposals";

export default function LabelingSessionPage() {
  const { id } = useParams();

  const [session, setSession] = useState<LabelingSession | null>(null);
  const [seeds, setSeeds] = useState<LabelingSeed[]>([]);
  const [verdicts, setVerdicts] = useState<LabelingVerdict[]>([]);
  const [sessionLinks, setSessionLinks] = useState<LabelingLink[]>([]);
  const [currentSeed, setCurrentSeed] = useState<LabelingSeed | null>(null);
  const [candidates, setCandidates] = useState<LabelingCandidate[]>([]);
  const [leftParty, setLeftParty] = useState<LabelingPartyView | null>(null);
  const [rightParty, setRightParty] = useState<LabelingPartyView | null>(null);
  const [pendingLinks, setPendingLinks] = useState<PendingLink[]>([]);
  const [linkKind, setLinkKind] = useState<LinkKind>("exact");
  const [rationale, setRationale] = useState("");

  const learnedPairs = useMemo(() => computeLearnedPairs(sessionLinks), [sessionLinks]);

  const reloadSession = useCallback(async () => {
    const s = await fetchApi<LabelingSession>(`/labeling/sessions/${id}`);
    setSession(s);
    const { seeds: ss } = await fetchApi<{ seeds: LabelingSeed[] }>(`/labeling/sessions/${id}/seeds`);
    setSeeds(ss);
    const { verdicts: vs } = await fetchApi<{ verdicts: LabelingVerdict[] }>(`/labeling/sessions/${id}/verdicts`);
    setVerdicts(vs);
    const { links: ls } = await fetchApi<{ links: LabelingLink[] }>(`/labeling/sessions/${id}/links`);
    setSessionLinks(ls);
  }, [id]);

  useEffect(() => { reloadSession(); }, [reloadSession]);

  async function runSeed(seed: LabelingSeed) {
    setCurrentSeed(seed);
    setRightParty(null);
    setPendingLinks([]);
    setRationale("");
    const r = await postApi<{
      seed: LabelingSeed;
      left_party: { source_id: string; side: "buyer" | "seller" };
      candidates: LabelingCandidate[];
    }>(`/labeling/sessions/${id}/seeds/${seed.id}/search`, {});
    setCandidates(r.candidates);
    const left = await fetchApi<LabelingPartyView>(
      `/labeling/party/${r.left_party.source_id}/${r.left_party.side}`
    );
    setLeftParty(left);
    reloadSession();
  }

  async function loadCandidate(c: LabelingCandidate) {
    const view = await fetchApi<LabelingPartyView>(`/labeling/party/${c.source_id}/${c.side}`);
    setRightParty(view);
    setRationale("");
    // Auto-propose: exact cross-field matches + previously-learned pairs.
    // User still reviews each before confirming.
    if (leftParty) {
      const exact = proposeExactLinks(leftParty, view);
      const learned = proposeLearnedLinks(leftParty, view, learnedPairs, exact);
      setPendingLinks([...exact, ...learned]);
    } else {
      setPendingLinks([]);
    }
    await postApi(`/labeling/sessions/${id}/reviewed`, { source_id: c.source_id, side: c.side });
  }

  async function submitVerdict(verdict: "confirmed" | "rejected" | "skip") {
    if (!rightParty || !leftParty) return;
    if (verdict === "skip") {
      await postApi(`/labeling/sessions/${id}/reviewed`, {
        source_id: rightParty.source_id, side: rightParty.side,
      });
    } else {
      await postApi(`/labeling/sessions/${id}/verdicts`, {
        source_id: rightParty.source_id,
        side: rightParty.side,
        verdict,
        left_source_id: leftParty.source_id,
        left_side: leftParty.side,
        seed_id: currentSeed?.id ?? null,
        rationale: rationale || null,
        links: verdict === "confirmed" ? stripAuto(pendingLinks) : [],
      });
    }
    // Advance to next unreviewed candidate
    const nextIdx = candidates.findIndex(
      (c) => c.source_id === rightParty.source_id && c.side === rightParty.side
    );
    const next = candidates.slice(nextIdx + 1).find(
      (c) => !verdicts.find((v) => v.source_id === c.source_id && v.side === c.side)
    );
    if (next) await loadCandidate(next);
    else setRightParty(null);
    reloadSession();
  }

  async function exportJson() {
    const token = localStorage.getItem("cleo_token");
    const res = await fetch(`/api/labeling/sessions/${id}/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `labeling-session-${id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!session) return <div className="p-6"><Text>Loading…</Text></div>;

  return (
    <div className="flex flex-col h-full" style={{ height: "100vh" }}>
      {/* Top bar */}
      <div className="h-10 flex items-center gap-4 px-4 border-b border-[var(--gray-4)]"
           style={{ background: "var(--gray-2)" }}>
        <Link to="/labeling" className="no-underline flex items-center gap-1"
              style={{ color: "var(--accent-11)" }}>
          <CaretLeft size={14} />
        </Link>
        <Heading size="3">{session.name}</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {session.display_id} · anchor {session.anchor_source_id}/{session.anchor_side}
        </Text>
        <div className="flex-1" />
        <Text size="1">{session.confirmed_count}✓ / {session.rejected_count}✗</Text>
        <Badge size="1" variant="soft">
          {session.seeds_by_state.pending ?? 0} seeds pending
        </Badge>
        <Button size="1" variant="soft" onClick={exportJson}>
          <DownloadSimple size={12} /> Export
        </Button>
      </div>

      {/* Body — four columns */}
      <div className="flex-1 flex overflow-hidden">
        <div className="w-[240px] border-r border-[var(--gray-4)] overflow-y-auto">
          <SeedQueuePanel
            sessionId={id!}
            seeds={seeds}
            verdicts={verdicts}
            currentSeedId={currentSeed?.id}
            onRunSeed={runSeed}
          />
        </div>

        <div className="flex-1 flex overflow-hidden relative">
          <div className="flex-1 p-4 overflow-auto border-r border-[var(--gray-4)]">
            {leftParty
              ? <PartyCard view={leftParty} side="left"
                           sharedHighlights={pendingLinks.map((l) => l.from_field_value)} />
              : <Text size="2" style={{ color: "var(--gray-9)" }}>
                  Pick a seed from the queue to start.
                </Text>}
          </div>
          <div className="flex-1 p-4 overflow-auto">
            {rightParty
              ? <PartyCard view={rightParty} side="right"
                           sharedHighlights={pendingLinks.map((l) => l.to_field_value)} />
              : <Text size="2" style={{ color: "var(--gray-9)" }}>
                  Pick a candidate from the list.
                </Text>}
          </div>
          <LinkCanvas links={pendingLinks} />
        </div>

        <div className="w-[300px] border-l border-[var(--gray-4)] overflow-y-auto">
          <CandidateListPanel
            candidates={candidates}
            verdicts={verdicts}
            currentRight={rightParty}
            onPick={loadCandidate}
          />
        </div>
      </div>

      {/* Action bar */}
      <VerdictBar
        linkKind={linkKind}
        setLinkKind={setLinkKind}
        rationale={rationale}
        setRationale={setRationale}
        disabled={!rightParty}
        pendingLinks={pendingLinks}
        setPendingLinks={setPendingLinks}
        onConfirm={() => submitVerdict("confirmed")}
        onReject={() => submitVerdict("rejected")}
        onSkip={() => submitVerdict("skip")}
      />
    </div>
  );
}
