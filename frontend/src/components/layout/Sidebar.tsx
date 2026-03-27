import { Link, useLocation } from "react-router-dom";
import { Heading } from "@radix-ui/themes";
import { Buildings, ChartBar, Users, UsersThree, Table, MapTrifold, Kanban, ListBullets, FlowArrow, ShieldCheck } from "@phosphor-icons/react";

const NAV_GROUPS = [
  {
    items: [
      { path: "/", label: "Dashboard", icon: ChartBar },
      { path: "/properties", label: "Properties", icon: Buildings },
      { path: "/transactions", label: "Transactions", icon: Table },
      { path: "/contacts", label: "Contacts", icon: Users },
      { path: "/groups", label: "Groups", icon: UsersThree },
      { path: "/map", label: "Map", icon: MapTrifold },
    ],
  },
  {
    label: "CRM",
    items: [
      { path: "/deals", label: "Deals", icon: Kanban },
      { path: "/lists", label: "Lists", icon: ListBullets },
    ],
  },
  {
    label: "Pipeline",
    items: [
      { path: "/pipeline", label: "Inspector", icon: FlowArrow },
      { path: "/data-quality", label: "Data Quality", icon: ShieldCheck },
    ],
  },
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <div className="app-sidebar flex flex-col border-r border-[var(--gray-4)]" style={{ background: "var(--gray-2)" }}>
      <div className="h-[var(--header-height)] flex items-center px-5 border-b border-[var(--gray-4)]">
        <Heading size="4" weight="medium">Cleo</Heading>
      </div>
      <nav className="flex flex-col gap-4 p-3">
        {NAV_GROUPS.map((group, gi) => (
          <div key={gi} className="flex flex-col gap-px">
            {group.label && (
              <div className="px-3 pt-2 pb-1 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>
                {group.label}
              </div>
            )}
            {group.items.map((item) => {
              const active = location.pathname === item.path ||
                (item.path !== "/" && location.pathname.startsWith(item.path));
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className="flex items-center gap-2 px-3 py-2 rounded-[var(--radius-2)] text-[14px] no-underline transition-colors"
                  style={{
                    background: active ? "var(--gray-a4)" : "transparent",
                    color: active ? "var(--gray-12)" : "var(--gray-11)",
                    fontWeight: active ? 500 : 400,
                  }}
                >
                  <Icon size={18} weight={active ? "fill" : "regular"} style={{ color: "var(--gray-a9)" }} />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </div>
  );
}
