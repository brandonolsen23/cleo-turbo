import { useSearchParams } from "react-router-dom";
import { Tabs } from "@radix-ui/themes";

export type AutoGroupTabValue = 'overview' | 'anchors' | 'parties' | 'graph' | 'trail';

const VALID_TABS: AutoGroupTabValue[] = ['overview', 'anchors', 'parties', 'graph', 'trail'];

interface Props {
  children: {
    overview: React.ReactNode;
    anchors:  React.ReactNode;
    parties:  React.ReactNode;
    graph:    React.ReactNode;
    trail:    React.ReactNode;
  };
}

export default function AutoGroupTabs({ children }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get('tab');
  const active: AutoGroupTabValue = (
    raw && VALID_TABS.includes(raw as AutoGroupTabValue) ? raw : 'overview'
  ) as AutoGroupTabValue;

  return (
    <Tabs.Root value={active}
               onValueChange={(v) => {
                 const next = new URLSearchParams(searchParams);
                 if (v === 'overview') next.delete('tab');
                 else next.set('tab', v);
                 setSearchParams(next, { replace: true });
               }}>
      <Tabs.List>
        <Tabs.Trigger value="overview">Overview</Tabs.Trigger>
        <Tabs.Trigger value="anchors">Anchor Tenures</Tabs.Trigger>
        <Tabs.Trigger value="parties">Parties</Tabs.Trigger>
        <Tabs.Trigger value="graph">Graph</Tabs.Trigger>
        <Tabs.Trigger value="trail">Trail</Tabs.Trigger>
      </Tabs.List>

      <div className="mt-5">
        <Tabs.Content value="overview">{children.overview}</Tabs.Content>
        <Tabs.Content value="anchors">{children.anchors}</Tabs.Content>
        <Tabs.Content value="parties">{children.parties}</Tabs.Content>
        <Tabs.Content value="graph">{children.graph}</Tabs.Content>
        <Tabs.Content value="trail">{children.trail}</Tabs.Content>
      </div>
    </Tabs.Root>
  );
}
