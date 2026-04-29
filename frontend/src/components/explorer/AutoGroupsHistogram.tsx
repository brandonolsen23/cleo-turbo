import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, Cell,
} from "recharts";
import { fetchApi } from "../../api/client";
import type { AutoGroupsHistogramResponse, AutoGroupsHistogramBucket } from "../../types";


function bucketColor(b: AutoGroupsHistogramBucket, confirmed: number, probable: number): string {
  if (b.lower >= confirmed) return "var(--jade-9)";
  if (b.lower >= probable)  return "var(--amber-9)";
  return "var(--gray-9)";
}

function bucketLabel(b: AutoGroupsHistogramBucket): string {
  return `${b.lower.toFixed(2)}–${b.upper.toFixed(2)}`;
}


export default function AutoGroupsHistogram() {
  const nav = useNavigate();
  const [data, setData] = useState<AutoGroupsHistogramResponse | null>(null);

  useEffect(() => {
    fetchApi<AutoGroupsHistogramResponse>(
      "/explorer/auto-groups/tuning/histogram",
    ).then(setData).catch(console.error);
  }, []);

  if (!data) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Heading size="3">Confidence histogram</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  const totalGroups = data.buckets.reduce((sum, b) => sum + b.count, 0);
  const chartData = data.buckets.map((b) => ({
    label: bucketLabel(b),
    count: b.count,
    bucket: b,
  }));

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-baseline gap-3 mb-2 flex-wrap">
        <Heading size="3">Confidence histogram</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {totalGroups.toLocaleString()} groups, 0.05-wide buckets. Click a bar to filter the list page.
        </Text>
      </div>

      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 30 }}>
            <XAxis dataKey="label" angle={-45} textAnchor="end" tick={{ fontSize: 10 }}
                   interval={0} height={60} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip
              formatter={(v: number) => [v.toLocaleString(), "groups"]}
              labelFormatter={(label: string) => `confidence ${label}`}
            />
            <ReferenceLine x={`${data.tier_probable_threshold.toFixed(2)}–${(data.tier_probable_threshold + 0.05).toFixed(2)}`}
                           stroke="var(--amber-11)" strokeDasharray="3 3"
                           label={{ value: "probable", position: "top", fontSize: 10 }} />
            <ReferenceLine x={`${data.tier_confirmed_threshold.toFixed(2)}–${(data.tier_confirmed_threshold + 0.05).toFixed(2)}`}
                           stroke="var(--jade-11)" strokeDasharray="3 3"
                           label={{ value: "confirmed", position: "top", fontSize: 10 }} />
            <Bar dataKey="count" cursor="pointer"
                 onClick={(d: { bucket?: AutoGroupsHistogramBucket }) => {
                   if (!d?.bucket) return;
                   const tier = d.bucket.lower >= data.tier_confirmed_threshold
                     ? "confirmed"
                     : d.bucket.lower >= data.tier_probable_threshold
                       ? "probable"
                       : "candidate";
                   nav(`/explorer/auto-groups?tier=${tier}`);
                 }}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={bucketColor(entry.bucket, data.tier_confirmed_threshold, data.tier_probable_threshold)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
