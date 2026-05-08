import { Text } from "@radix-ui/themes";
import type { AIPageContext } from "../../types";

const PROMPTS_PROPERTY = [
  "Tell me about this owner",
  "Recent comparable sales nearby",
  "Other properties this owner has bought",
];

const PROMPTS_PEOPLE = [
  "What does their portfolio look like?",
  "What have they bought recently?",
  "Who else are they affiliated with?",
];

const PROMPTS_OPEN = [
  "Find retail buyers in Halton with $20M+ portfolios",
  "Who's been most active in Brantford this year?",
  "Show me dormant contacts I should re-engage",
];

function chooseSet(ctx: AIPageContext | null): string[] {
  if (!ctx) return PROMPTS_OPEN;
  if (ctx.entity_type === "property") return PROMPTS_PROPERTY;
  if (ctx.entity_type === "contact" || ctx.entity_type === "group") return PROMPTS_PEOPLE;
  return PROMPTS_OPEN;
}

export default function SuggestedPrompts({
  context,
  onPick,
}: {
  context: AIPageContext | null;
  onPick: (prompt: string) => void;
}) {
  const prompts = chooseSet(context);
  return (
    <div className="flex flex-col gap-2">
      <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-1">Try asking:</Text>
      {prompts.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onPick(p)}
          className="text-left px-3 py-2 rounded border border-[var(--gray-6)] hover:bg-[var(--gray-2)] text-[13px]"
        >
          {p}
        </button>
      ))}
    </div>
  );
}
