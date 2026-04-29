import { Heading, Text } from "@radix-ui/themes";
import { Link } from "react-router-dom";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import AutoGroupsHistogram from "../components/explorer/AutoGroupsHistogram";
import AutoGroupsCloseToPromotion from "../components/explorer/AutoGroupsCloseToPromotion";
import AutoGroupsMissedStems from "../components/explorer/AutoGroupsMissedStems";


export default function ExplorerAutoGroupsTuning() {
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <Link to="/explorer/auto-groups" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Auto-Groups
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-5 flex-wrap">
        <Heading size="6">Tuning</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          See how the algorithm distributes confidence, find groups close to promotion, and inspect 1-grams that didn't promote.
        </Text>
      </div>

      <div className="flex flex-col gap-8">
        <AutoGroupsHistogram />
        <AutoGroupsCloseToPromotion />
        <AutoGroupsMissedStems />
      </div>
    </div>
  );
}
