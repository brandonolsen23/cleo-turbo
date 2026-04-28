import { Text } from "@radix-ui/themes";

export default function AutoGroupTabPlaceholder({ planName }: { planName: string }) {
  return (
    <div className="p-8 rounded-[var(--card-radius)] border border-[var(--gray-6)]"
         style={{ background: "var(--gray-2)" }}>
      <Text size="3" style={{ color: "var(--gray-9)" }}>
        Coming in {planName}.
      </Text>
    </div>
  );
}
