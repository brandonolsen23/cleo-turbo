import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import type { DashboardStats } from "../types";

export default function DashboardPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    fetchApi<DashboardStats>("/properties/stats").then(setStats);
  }, []);

  if (!stats) return <Text>Loading...</Text>;

  const cards = [
    { label: "Properties", value: stats.total_properties.toLocaleString() },
    { label: "Transactions", value: stats.total_transactions.toLocaleString() },
    { label: "Contacts", value: stats.total_contacts.toLocaleString() },
    { label: "Groups", value: stats.total_groups.toLocaleString() },
  ];

  const engagedCards = [
    { label: "Engaged Contacts", value: stats.engaged_contacts.toLocaleString(), total: stats.total_contacts },
    { label: "Engaged Groups", value: stats.engaged_groups.toLocaleString(), total: stats.total_groups },
  ];

  // Build chart data from top cities
  const cityChartData = stats.top_cities?.slice(0, 12).map((c) => ({
    name: c.city.length > 12 ? c.city.slice(0, 12) + "..." : c.city,
    properties: c.count,
  })) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <Heading size="5" weight="medium">Dashboard</Heading>

      {/* Primary stat cards */}
      <div className="grid grid-cols-4 gap-4">
        {cards.map((c) => (
          <div key={c.label} className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="2" style={{ color: "var(--gray-9)" }}>{c.label}</Text>
            <Heading size="6" weight="medium" className="mt-1">{c.value}</Heading>
          </div>
        ))}
      </div>

      {/* Engaged + Chart row */}
      <div className="grid grid-cols-3 gap-4">
        {/* Engaged cards */}
        <div className="flex flex-col gap-4">
          {engagedCards.map((c) => (
            <div key={c.label} className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
              <Text size="2" style={{ color: "var(--gray-9)" }}>{c.label}</Text>
              <div className="flex items-baseline gap-2 mt-1">
                <Heading size="5" weight="medium">{c.value}</Heading>
                <Text size="2" style={{ color: "var(--gray-9)" }}>of {c.total.toLocaleString()}</Text>
              </div>
              <div className="h-1.5 rounded-full mt-2" style={{ background: "var(--gray-4)" }}>
                <div
                  className="h-1.5 rounded-full"
                  style={{
                    background: "var(--jade-9)",
                    width: `${c.total > 0 ? (Number(c.value.replace(/,/g, "")) / c.total) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Properties by City chart */}
        <div className="col-span-2 rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Properties by City</Text>
          {cityChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={cityChartData} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-4)" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--gray-9)" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "var(--gray-9)" }} axisLine={false} tickLine={false}
                       tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)} />
                <Tooltip
                  contentStyle={{ borderRadius: 8, border: "1px solid var(--gray-6)", fontSize: 13 }}
                  formatter={(value) => [Number(value).toLocaleString(), "Properties"]}
                />
                <Bar dataKey="properties" fill="var(--jade-9)" radius={[3, 3, 0, 0]} barSize={24} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <Text size="2" style={{ color: "var(--gray-9)" }}>No data</Text>
          )}
        </div>
      </div>

      {/* Recent Transactions + Top Cities */}
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Recent Transactions</Text>
          <table className="w-full text-[14px]">
            <thead>
              <tr className="border-b border-[var(--gray-4)]">
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Date</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Address</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>City</th>
                <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_transactions?.map((t) => (
                <tr key={t.source_id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                    onClick={() => navigate(`/transactions/${t.source_id}`)}>
                  <td className="py-2">{formatDate(t.sale_date)}</td>
                  <td className="py-2">{t.display_address}</td>
                  <td className="py-2">{t.city}</td>
                  <td className="py-2 text-right">{formatCurrency(t.sale_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Top Cities</Text>
          <div className="flex flex-col gap-2">
            {stats.top_cities?.slice(0, 10).map((c) => {
              const maxCount = stats.top_cities[0]?.count ?? 1;
              return (
                <div key={c.city} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[13px]">
                    <span>{c.city}</span>
                    <span style={{ color: "var(--gray-9)" }}>{c.count.toLocaleString()}</span>
                  </div>
                  <div className="h-1 rounded-full" style={{ background: "var(--gray-4)" }}>
                    <div
                      className="h-1 rounded-full"
                      style={{ background: "var(--jade-9)", width: `${(c.count / maxCount) * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
