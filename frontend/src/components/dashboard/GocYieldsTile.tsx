import { useEffect, useState } from "react";
import { Text, Heading, Popover, IconButton } from "@radix-ui/themes";
import { Info, CaretUp, CaretDown } from "@phosphor-icons/react";
import { LineChart, Line, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { fetchApi } from "../../api/client";
import type { GocRates, GocTerm } from "../../types";

const TERM_LABELS: Record<GocTerm, string> = {
  "2yr": "2yr",
  "5yr": "5yr",
  "10yr": "10yr",
  long: "Long",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

// Yields up = more expensive to borrow = red; down = cheaper = green.
function deltaColor(bps: number | null): string {
  if (bps === null || bps === 0) return "var(--gray-9)";
  return bps > 0 ? "var(--red-11)" : "var(--green-11)";
}

function toBps(pts: number | null): number | null {
  return pts === null || pts === undefined ? null : Math.round(pts * 100);
}

function DeltaBadge({ pts, label }: { pts: number | null; label: string }) {
  const bps = toBps(pts);
  const color = deltaColor(bps);
  return (
    <div className="flex items-center gap-1">
      {bps !== null && bps !== 0 &&
        (bps > 0
          ? <CaretUp size={11} weight="fill" color={color} />
          : <CaretDown size={11} weight="fill" color={color} />)}
      <Text size="1" style={{ color }}>
        {bps === null ? "—" : `${bps > 0 ? "+" : ""}${bps} bps`}
      </Text>
      <Text size="1" style={{ color: "var(--gray-8)" }}>{label}</Text>
    </div>
  );
}

function InfoPopover() {
  return (
    <Popover.Root>
      <Popover.Trigger>
        <IconButton size="1" variant="ghost" color="gray" radius="full"
          aria-label="About GoC bond yields">
          <Info size={15} />
        </IconButton>
      </Popover.Trigger>
      <Popover.Content width="360px">
        <div className="flex flex-col gap-2">
          <Text size="2" weight="medium">How to read this</Text>
          <Text size="1" style={{ color: "var(--gray-11)" }}>
            These are Government of Canada (GoC) benchmark bond yields, the
            return on federal debt and the base rate commercial mortgages are
            priced from. A fixed quote is roughly the GoC yield for the matching
            term plus a lender spread. When yields rise, financing gets more
            expensive and property values face downward pressure. When they
            fall, the reverse.
          </Text>
          <Text size="1" weight="medium">Terms</Text>
          <Text size="1" style={{ color: "var(--gray-11)" }}>
            <b>5yr</b>: the workhorse. Most commercial and CMHC financing prices
            off it. Watch this one.<br />
            <b>2yr</b>: tracks near-term Bank of Canada rate expectations, the
            most policy-sensitive.<br />
            <b>10yr</b>: longer-term financing and a long-run growth and
            inflation read.<br />
            <b>Long</b>: 30-year horizon, the market's long-run inflation view.
          </Text>
          <Text size="1" weight="medium">Timeframes and the mini chart</Text>
          <Text size="1" style={{ color: "var(--gray-11)" }}>
            1d / 1w / 1m are the change over the last day, week, and month in
            basis points (bps). 1 bps = 0.01%. A move of 20+ bps in a week is
            meaningful, a few bps is noise. The mini chart is the 5yr over 90
            days, and the trend matters more than any single day's number.
          </Text>
          <Text size="1" style={{ color: "var(--gray-11)" }}>
            "Since BoC" is the change since the Bank of Canada's last rate
            decision, a read on how far the market has repriced since the Bank
            last acted. The Bank sets the overnight rate on 8 fixed dates a
            year, and these yields often move ahead of it.
          </Text>
          <Text size="1" style={{ color: "var(--gray-11)" }}>
            <span style={{ color: "var(--red-11)" }}>Red = up</span> (more
            expensive to borrow),{" "}
            <span style={{ color: "var(--green-11)" }}>green = down</span>{" "}
            (cheaper). Yields update on business days only, with a short lag, so
            weekends and holidays show the last close.
          </Text>
        </div>
      </Popover.Content>
    </Popover.Root>
  );
}

export default function GocYieldsTile() {
  const [rates, setRates] = useState<GocRates | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchApi<GocRates>("/rates/goc").then(setRates).catch(() => setFailed(true));
  }, []);

  const five = rates?.terms?.["5yr"];
  const secondary: GocTerm[] = ["2yr", "10yr", "long"];

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Text size="2" weight="medium" style={{ color: "var(--gray-11)" }}>
            GoC 5yr benchmark yield
          </Text>
          <InfoPopover />
        </div>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          As of {fmtDate(rates?.as_of ?? null)} · Bank of Canada
        </Text>
      </div>

      {failed || (rates && !five) ? (
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Bond yields unavailable right now. They populate on app startup when a
          connection is available.
        </Text>
      ) : !rates ? (
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      ) : (
        <div className="grid grid-cols-3 gap-4 items-center">
          <div className="col-span-1">
            <div className="flex items-baseline gap-1">
              <Heading size="7" weight="medium">{five!.yield.toFixed(2)}</Heading>
              <Text size="3" style={{ color: "var(--gray-9)" }}>%</Text>
            </div>
            <div className="flex flex-col gap-0.5 mt-1">
              <DeltaBadge pts={five!.change_1d} label="1d" />
              <DeltaBadge pts={five!.change_1w} label="1w" />
              <DeltaBadge pts={five!.change_1m} label="1m" />
              <DeltaBadge pts={five!.change_since_boc} label="since BoC" />
            </div>
          </div>

          <div className="col-span-2">
            {rates.history.length > 1 ? (
              <ResponsiveContainer width="100%" height={64}>
                <LineChart data={rates.history}
                  margin={{ top: 6, right: 4, bottom: 6, left: 4 }}>
                  <YAxis hide domain={["dataMin", "dataMax"]} />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: "1px solid var(--gray-6)",
                      fontSize: 12, padding: "4px 8px" }}
                    labelFormatter={(l) => fmtDate(String(l))}
                    formatter={(v) => [`${Number(v).toFixed(2)}%`, "5yr"]}
                  />
                  <Line type="monotone" dataKey="yield" stroke="var(--jade-9)"
                    strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                Building 90-day history…
              </Text>
            )}
            <Text size="1" style={{ color: "var(--gray-8)" }}
              className="block text-right">90-day trend</Text>
          </div>
        </div>
      )}

      {rates && five && (
        <div className="flex items-center gap-6 mt-4 pt-3 border-t border-[var(--gray-4)]">
          {secondary.map((t) => {
            const y = rates.terms[t];
            if (!y) return null;
            const bps = toBps(y.change_1d);
            return (
              <div key={t} className="flex items-baseline gap-2">
                <Text size="1" style={{ color: "var(--gray-9)" }}>{TERM_LABELS[t]}</Text>
                <Text size="2" weight="medium">{y.yield.toFixed(2)}%</Text>
                <Text size="1" style={{ color: deltaColor(bps) }}>
                  {bps === null ? "" : `${bps > 0 ? "+" : ""}${bps}`}
                </Text>
              </div>
            );
          })}
        </div>
      )}

      {rates && (rates.last_boc || rates.next_boc) && (
        <Text size="1" style={{ color: "var(--gray-8)" }} className="block mt-2">
          {rates.last_boc ? `Last BoC decision ${fmtDate(rates.last_boc)}` : ""}
          {rates.next_boc ? ` · Next ${fmtDate(rates.next_boc)}` : ""}
        </Text>
      )}
    </div>
  );
}
