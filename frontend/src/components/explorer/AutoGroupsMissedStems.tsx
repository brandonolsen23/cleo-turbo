import { Heading, Text } from "@radix-ui/themes";

export default function AutoGroupsMissedStems() {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5"
         style={{ background: "var(--gray-2)" }}>
      <Heading size="3">Stems that didn't promote</Heading>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        Coming in Task 8.
      </Text>
    </div>
  );
}
