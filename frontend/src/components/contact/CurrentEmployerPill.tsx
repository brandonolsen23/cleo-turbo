import { Badge } from "@radix-ui/themes";
import { LinkedinLogo, Buildings, WarningCircle } from "@phosphor-icons/react";
import type { CurrentEmployer } from "../../types";

export default function CurrentEmployerPill({
  employer,
}: {
  employer: CurrentEmployer | null;
}) {
  if (!employer) return null;

  const labelText = employer.display_name || employer.company || "—";

  if (employer.source === "linkedin_confirmed") {
    return (
      <Badge color="jade" variant="soft" size="2">
        <LinkedinLogo size={12} weight="fill" />
        {labelText} · LinkedIn-confirmed
      </Badge>
    );
  }

  if (employer.source === "linkedin_diverges") {
    return (
      <Badge color="amber" variant="soft" size="2">
        <LinkedinLogo size={12} weight="fill" />
        {labelText}
        <WarningCircle size={12} />
        diverges from Realtrack
      </Badge>
    );
  }

  if (employer.source === "linkedin") {
    return (
      <Badge color="jade" variant="soft" size="2">
        <LinkedinLogo size={12} weight="fill" />
        {labelText}
      </Badge>
    );
  }

  // realtrack
  return (
    <Badge color="gray" variant="soft" size="2">
      <Buildings size={12} />
      {labelText}
    </Badge>
  );
}
