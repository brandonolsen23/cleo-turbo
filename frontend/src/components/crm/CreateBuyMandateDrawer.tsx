/**
 * CreateBuyMandateDrawer — full-criteria drawer for creating/editing buy mandates.
 *
 * Replaces the old CreateBuyMandateDialog. Opens as a slide-in drawer with all
 * criteria fields organized into collapsible sections. Same component is used
 * for both create and edit modes.
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Heading,
  Text,
  TextArea,
  TextField,
  Badge,
  Select,
  Separator,
} from "@radix-ui/themes";
import {
  X,
  CaretDown,
  CaretRight,
  Buildings,
  MapPin,
  CurrencyDollar,
  Ruler,
  ChartLineUp,
  Clock,
  Users,
  Notepad,
} from "@phosphor-icons/react";
import { fetchApi, postApi, mutateApi } from "../../api/client";
import { formatCurrency } from "../../lib/utils";
import type {
  BuyMandateCriteria,
  AssetClassesResponse,
  TenantCategoriesResponse,
  TenantQuality,
  OccupancyType,
  AnchoredPreference,
  MarketTier,
  InvestmentStrategy,
  VacancyTolerance,
  MandatePriority,
  MandateTimeline,
} from "../../types";

// ── Label maps for enums ──

const TENANT_QUALITY_OPTIONS: { value: TenantQuality; label: string }[] = [
  { value: "national_credit", label: "National Credit (AAA)" },
  { value: "regional_credit", label: "Regional Credit" },
  { value: "local", label: "Local" },
  { value: "any", label: "Any" },
];

const OCCUPANCY_OPTIONS: { value: OccupancyType; label: string }[] = [
  { value: "single", label: "Single Tenant" },
  { value: "multi", label: "Multi-Tenant" },
  { value: "either", label: "Either" },
];

const ANCHORED_OPTIONS: { value: AnchoredPreference; label: string }[] = [
  { value: "grocery", label: "Grocery Anchored" },
  { value: "big_box", label: "Big Box Anchored" },
  { value: "none", label: "No Preference" },
];

const MARKET_TIER_OPTIONS: { value: MarketTier; label: string }[] = [
  { value: "primary", label: "Primary" },
  { value: "secondary", label: "Secondary" },
  { value: "tertiary", label: "Tertiary" },
];

const STRATEGY_OPTIONS: { value: InvestmentStrategy; label: string }[] = [
  { value: "core", label: "Core" },
  { value: "core_plus", label: "Core-Plus" },
  { value: "value_add", label: "Value-Add" },
  { value: "opportunistic", label: "Opportunistic" },
];

const VACANCY_OPTIONS: { value: VacancyTolerance; label: string }[] = [
  { value: "fully_leased", label: "Fully Leased Only" },
  { value: "some_vacancy", label: "Some Vacancy OK" },
  { value: "high_vacancy", label: "High Vacancy / Value-Add" },
];

const PRIORITY_OPTIONS: { value: MandatePriority; label: string }[] = [
  { value: "primary", label: "Primary" },
  { value: "secondary", label: "Secondary" },
  { value: "exploratory", label: "Exploratory" },
];

const TIMELINE_OPTIONS: { value: MandateTimeline; label: string }[] = [
  { value: "immediate", label: "Immediate (0–3 months)" },
  { value: "near_term", label: "Near-term (3–6 months)" },
  { value: "medium", label: "Medium (6–12 months)" },
  { value: "long_term", label: "Long-term (12+ months)" },
];

// ── Props ──

interface CreateBuyMandateDrawerProps {
  contactId?: string;
  groupId?: string;
  entityName: string;
  onClose: () => void;
  /** If provided, drawer is in edit mode for this mandate */
  editMandateId?: string;
  editCriteria?: BuyMandateCriteria;
  editNotes?: string;
}

// ── Collapsible Section ──

function Section({
  icon,
  title,
  defaultOpen = true,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-[var(--gray-4)]">
      <button
        type="button"
        className="flex items-center gap-2 w-full px-5 py-3 hover:bg-[var(--gray-2)] transition-colors text-left"
        onClick={() => setOpen(!open)}
      >
        {open ? <CaretDown size={14} style={{ color: "var(--gray-9)" }} /> : <CaretRight size={14} style={{ color: "var(--gray-9)" }} />}
        <span style={{ color: "var(--gray-9)" }}>{icon}</span>
        <Text size="2" weight="medium">{title}</Text>
      </button>
      {open && <div className="px-5 pb-4 space-y-3">{children}</div>}
    </div>
  );
}

// ── Chip multi-select ──

function ChipSelect({
  options,
  selected,
  onChange,
  size = "1",
}: {
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (sel: string[]) => void;
  size?: "1" | "2";
}) {
  const toggle = (val: string) => {
    if (selected.includes(val)) {
      onChange(selected.filter((v) => v !== val));
    } else {
      onChange([...selected, val]);
    }
  };

  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((opt) => {
        const isSelected = selected.includes(opt.value);
        return (
          <Badge
            key={opt.value}
            size={size}
            variant={isSelected ? "solid" : "outline"}
            color={isSelected ? "jade" : "gray"}
            className="cursor-pointer select-none"
            onClick={() => toggle(opt.value)}
            style={!isSelected ? { borderColor: "var(--gray-6)" } : undefined}
          >
            {opt.label}
          </Badge>
        );
      })}
    </div>
  );
}

// ── Field label ──

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <Text size="1" weight="medium" className="block mb-1" style={{ color: "var(--gray-9)" }}>
      {children}
    </Text>
  );
}

// ── Range input (two inline fields) ──

function RangeInput({
  minValue,
  maxValue,
  onMinChange,
  onMaxChange,
  prefix = "",
  placeholder = ["Min", "Max"],
  type = "number",
}: {
  minValue: string;
  maxValue: string;
  onMinChange: (v: string) => void;
  onMaxChange: (v: string) => void;
  prefix?: string;
  placeholder?: [string, string];
  type?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1">
        <TextField.Root
          size="2"
          type={type}
          value={minValue}
          onChange={(e) => onMinChange(e.target.value)}
          placeholder={placeholder[0]}
        >
          {prefix && <TextField.Slot side="left"><Text size="1" style={{ color: "var(--gray-9)" }}>{prefix}</Text></TextField.Slot>}
        </TextField.Root>
      </div>
      <Text size="2" style={{ color: "var(--gray-9)" }}>–</Text>
      <div className="flex-1">
        <TextField.Root
          size="2"
          type={type}
          value={maxValue}
          onChange={(e) => onMaxChange(e.target.value)}
          placeholder={placeholder[1]}
        >
          {prefix && <TextField.Slot side="left"><Text size="1" style={{ color: "var(--gray-9)" }}>{prefix}</Text></TextField.Slot>}
        </TextField.Root>
      </div>
    </div>
  );
}

// ── Main Component ──

export default function CreateBuyMandateDrawer({
  contactId,
  groupId,
  entityName,
  onClose,
  editMandateId,
  editCriteria,
  editNotes,
}: CreateBuyMandateDrawerProps) {
  const navigate = useNavigate();
  const isEditMode = !!editMandateId;

  // ── Taxonomy data ──
  const [assetClasses, setAssetClasses] = useState<AssetClassesResponse | null>(null);
  const [tenantCategories, setTenantCategories] = useState<TenantCategoriesResponse | null>(null);

  useEffect(() => {
    fetchApi<AssetClassesResponse>("/asset-classes").then(setAssetClasses);
    fetchApi<TenantCategoriesResponse>("/tenant-categories").then(setTenantCategories);
  }, []);

  // ── Form state ──
  const [criteria, setCriteria] = useState<BuyMandateCriteria>(editCriteria || {});
  const [notes, setNotes] = useState(editNotes || "");
  const [saving, setSaving] = useState(false);

  // Convenience updater
  const updateCriteria = useCallback(<K extends keyof BuyMandateCriteria>(key: K, value: BuyMandateCriteria[K]) => {
    setCriteria((prev) => {
      // Remove field if value is empty/null/undefined/empty-array
      if (value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0)) {
        const next = { ...prev };
        delete next[key];
        return next;
      }
      return { ...prev, [key]: value };
    });
  }, []);

  // Number field helpers — store as string for editing, convert on save
  const [priceMinStr, setPriceMinStr] = useState(editCriteria?.price_min?.toString() || "");
  const [priceMaxStr, setPriceMaxStr] = useState(editCriteria?.price_max?.toString() || "");
  const [capMinStr, setCapMinStr] = useState(editCriteria?.cap_rate_min?.toString() || "");
  const [capMaxStr, setCapMaxStr] = useState(editCriteria?.cap_rate_max?.toString() || "");
  const [noiMinStr, setNoiMinStr] = useState(editCriteria?.noi_min?.toString() || "");
  const [noiMaxStr, setNoiMaxStr] = useState(editCriteria?.noi_max?.toString() || "");
  const [sqftMinStr, setSqftMinStr] = useState(editCriteria?.sqft_min?.toString() || "");
  const [sqftMaxStr, setSqftMaxStr] = useState(editCriteria?.sqft_max?.toString() || "");
  const [acreMinStr, setAcreMinStr] = useState(editCriteria?.acreage_min?.toString() || "");
  const [acreMaxStr, setAcreMaxStr] = useState(editCriteria?.acreage_max?.toString() || "");
  const [unitMinStr, setUnitMinStr] = useState(editCriteria?.unit_count_min?.toString() || "");
  const [unitMaxStr, setUnitMaxStr] = useState(editCriteria?.unit_count_max?.toString() || "");

  // ── Derived state ──
  const selectedAssetClasses = criteria.asset_classes || [];
  const showRetailOptions = selectedAssetClasses.includes("retail");
  const showLandOptions = selectedAssetClasses.includes("land") || selectedAssetClasses.includes("agricultural");
  const showMultifamilyOptions = selectedAssetClasses.includes("multifamily");

  // Filter subclasses to show only children of selected asset classes
  const availableSubclasses =
    assetClasses?.classes
      .filter((ac) => selectedAssetClasses.includes(ac.id))
      .flatMap((ac) => ac.subcategories.map((sc) => ({ value: sc.id, label: sc.label }))) || [];

  // ── Save ──
  async function handleSave() {
    setSaving(true);

    // Build final criteria with number conversions
    const finalCriteria: BuyMandateCriteria = { ...criteria };
    const parseNum = (s: string) => { const n = Number(s); return isNaN(n) || s === "" ? undefined : n; };
    const parseFloat_ = (s: string) => { const n = parseFloat(s); return isNaN(n) || s === "" ? undefined : n; };

    finalCriteria.price_min = parseNum(priceMinStr);
    finalCriteria.price_max = parseNum(priceMaxStr);
    finalCriteria.cap_rate_min = parseFloat_(capMinStr);
    finalCriteria.cap_rate_max = parseFloat_(capMaxStr);
    finalCriteria.noi_min = parseNum(noiMinStr);
    finalCriteria.noi_max = parseNum(noiMaxStr);
    finalCriteria.sqft_min = parseNum(sqftMinStr);
    finalCriteria.sqft_max = parseNum(sqftMaxStr);
    finalCriteria.acreage_min = parseFloat_(acreMinStr);
    finalCriteria.acreage_max = parseFloat_(acreMaxStr);
    finalCriteria.unit_count_min = parseNum(unitMinStr);
    finalCriteria.unit_count_max = parseNum(unitMaxStr);

    // Clean up undefined values
    const cleanCriteria = Object.fromEntries(
      Object.entries(finalCriteria).filter(([, v]) => v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && v.length === 0))
    );

    try {
      if (isEditMode) {
        await mutateApi(`/buy-mandates/${editMandateId}`, "PATCH", {
          criteria: cleanCriteria,
          notes: notes || null,
        });
        onClose();
      } else {
        const result = await postApi<{ id: string }>("/buy-mandates", {
          contact_id: contactId || null,
          group_id: groupId || null,
          criteria: cleanCriteria,
          notes: notes || null,
        });
        navigate(`/opportunities/buy/${result.id}`);
      }
    } catch {
      setSaving(false);
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40 transition-opacity duration-200"
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        className="fixed top-0 right-0 bottom-0 z-50 flex flex-col bg-white shadow-xl"
        style={{
          width: 600,
          backgroundColor: "var(--color-background)",
          boxShadow: "var(--shadow-6)",
        }}
      >
        {/* Fixed header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b shrink-0"
          style={{ borderColor: "var(--gray-4)" }}
        >
          <div>
            <Heading size="4">{isEditMode ? "Edit Buy Mandate" : "New Buy Mandate"}</Heading>
            <Text size="2" style={{ color: "var(--gray-9)" }}>
              Buyer: {entityName}
            </Text>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-[var(--gray-3)] transition-colors"
          >
            <X size={18} style={{ color: "var(--gray-9)" }} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">

          {/* ── Property Type ── */}
          <Section icon={<Buildings size={16} />} title="Property Type">
            <FieldLabel>Asset Classes</FieldLabel>
            {assetClasses && (
              <ChipSelect
                options={assetClasses.classes.map((ac) => ({ value: ac.id, label: ac.label }))}
                selected={selectedAssetClasses}
                onChange={(v) => {
                  updateCriteria("asset_classes", v);
                  // Clear subclasses that are no longer valid
                  if (criteria.asset_subclasses?.length) {
                    const validParents = new Set(v);
                    const validSubs = assetClasses.classes
                      .filter((ac) => validParents.has(ac.id))
                      .flatMap((ac) => ac.subcategories.map((sc) => sc.id));
                    const validSubSet = new Set(validSubs);
                    const filtered = criteria.asset_subclasses.filter((s) => validSubSet.has(s));
                    updateCriteria("asset_subclasses", filtered);
                  }
                }}
              />
            )}

            {availableSubclasses.length > 0 && (
              <>
                <FieldLabel>Subclasses</FieldLabel>
                <ChipSelect
                  options={availableSubclasses}
                  selected={criteria.asset_subclasses || []}
                  onChange={(v) => updateCriteria("asset_subclasses", v)}
                />
              </>
            )}

            <FieldLabel>Zoning Requirements</FieldLabel>
            <TextArea
              size="2"
              rows={2}
              value={criteria.zoning_notes || ""}
              onChange={(e) => updateCriteria("zoning_notes", e.target.value || undefined)}
              placeholder='e.g., "Must be zoned C2 or higher", "Needs drive-through zoning"'
            />
          </Section>

          {/* ── Tenant Preferences ── */}
          <Section icon={<Users size={16} />} title="Tenant Preferences">
            <FieldLabel>Tenant Quality</FieldLabel>
            <Select.Root
              value={criteria.tenant_quality || ""}
              onValueChange={(v) => updateCriteria("tenant_quality", (v || undefined) as TenantQuality | undefined)}
            >
              <Select.Trigger placeholder="Select quality..." variant="soft" className="w-full" />
              <Select.Content>
                {TENANT_QUALITY_OPTIONS.map((o) => (
                  <Select.Item key={o.value} value={o.value}>{o.label}</Select.Item>
                ))}
              </Select.Content>
            </Select.Root>

            <FieldLabel>Tenant Categories</FieldLabel>
            {tenantCategories && (
              <div className="space-y-2">
                {tenantCategories.categories.map((cat) => (
                  <div key={cat.id}>
                    <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-1">
                      {cat.label}
                    </Text>
                    <ChipSelect
                      options={cat.subcategories.map((sc) => ({ value: sc.id, label: sc.label }))}
                      selected={criteria.tenant_categories || []}
                      onChange={(v) => updateCriteria("tenant_categories", v)}
                    />
                  </div>
                ))}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <FieldLabel>Occupancy Type</FieldLabel>
                <Select.Root
                  value={criteria.occupancy_type || ""}
                  onValueChange={(v) => updateCriteria("occupancy_type", (v || undefined) as OccupancyType | undefined)}
                >
                  <Select.Trigger placeholder="Any" variant="soft" className="w-full" />
                  <Select.Content>
                    {OCCUPANCY_OPTIONS.map((o) => (
                      <Select.Item key={o.value} value={o.value}>{o.label}</Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </div>

              {showRetailOptions && (
                <div>
                  <FieldLabel>Anchored Preference</FieldLabel>
                  <Select.Root
                    value={criteria.anchored_preference || ""}
                    onValueChange={(v) => updateCriteria("anchored_preference", (v || undefined) as AnchoredPreference | undefined)}
                  >
                    <Select.Trigger placeholder="Any" variant="soft" className="w-full" />
                    <Select.Content>
                      {ANCHORED_OPTIONS.map((o) => (
                        <Select.Item key={o.value} value={o.value}>{o.label}</Select.Item>
                      ))}
                    </Select.Content>
                  </Select.Root>
                </div>
              )}
            </div>
          </Section>

          {/* ── Location ── */}
          <Section icon={<MapPin size={16} />} title="Location">
            <FieldLabel>Market Tiers</FieldLabel>
            <ChipSelect
              options={MARKET_TIER_OPTIONS}
              selected={criteria.market_tiers || []}
              onChange={(v) => updateCriteria("market_tiers", v as MarketTier[])}
            />

            <FieldLabel>Regions</FieldLabel>
            <TextArea
              size="2"
              rows={2}
              value={(criteria.regions || []).join(", ")}
              onChange={(e) => {
                const vals = e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean);
                updateCriteria("regions", vals);
              }}
              placeholder="Comma-separated: Metro Toronto, Peel Region, York Region..."
            />

            <FieldLabel>Cities</FieldLabel>
            <TextArea
              size="2"
              rows={2}
              value={(criteria.cities || []).join(", ")}
              onChange={(e) => {
                const vals = e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean);
                updateCriteria("cities", vals);
              }}
              placeholder="Comma-separated: London, Hamilton, Kitchener..."
            />
          </Section>

          {/* ── Financial ── */}
          <Section icon={<CurrencyDollar size={16} />} title="Financial">
            <FieldLabel>Price Range</FieldLabel>
            <RangeInput
              prefix="$"
              minValue={priceMinStr}
              maxValue={priceMaxStr}
              onMinChange={setPriceMinStr}
              onMaxChange={setPriceMaxStr}
              placeholder={["Min price", "Max price"]}
            />

            <FieldLabel>Cap Rate Range (%)</FieldLabel>
            <RangeInput
              minValue={capMinStr}
              maxValue={capMaxStr}
              onMinChange={setCapMinStr}
              onMaxChange={setCapMaxStr}
              placeholder={["Min %", "Max %"]}
            />

            <FieldLabel>NOI Range</FieldLabel>
            <RangeInput
              prefix="$"
              minValue={noiMinStr}
              maxValue={noiMaxStr}
              onMinChange={setNoiMinStr}
              onMaxChange={setNoiMaxStr}
              placeholder={["Min NOI", "Max NOI"]}
            />
          </Section>

          {/* ── Size & Physical ── */}
          <Section icon={<Ruler size={16} />} title="Size & Physical">
            <FieldLabel>Building Size (sqft)</FieldLabel>
            <RangeInput
              minValue={sqftMinStr}
              maxValue={sqftMaxStr}
              onMinChange={setSqftMinStr}
              onMaxChange={setSqftMaxStr}
              placeholder={["Min sqft", "Max sqft"]}
            />

            {showLandOptions && (
              <>
                <FieldLabel>Acreage</FieldLabel>
                <RangeInput
                  minValue={acreMinStr}
                  maxValue={acreMaxStr}
                  onMinChange={setAcreMinStr}
                  onMaxChange={setAcreMaxStr}
                  placeholder={["Min acres", "Max acres"]}
                />
              </>
            )}

            {showMultifamilyOptions && (
              <>
                <FieldLabel>Unit Count</FieldLabel>
                <RangeInput
                  minValue={unitMinStr}
                  maxValue={unitMaxStr}
                  onMinChange={setUnitMinStr}
                  onMaxChange={setUnitMaxStr}
                  placeholder={["Min units", "Max units"]}
                />
              </>
            )}
          </Section>

          {/* ── Investment Profile ── */}
          <Section icon={<ChartLineUp size={16} />} title="Investment Profile">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <FieldLabel>Strategy</FieldLabel>
                <Select.Root
                  value={criteria.investment_strategy || ""}
                  onValueChange={(v) => updateCriteria("investment_strategy", (v || undefined) as InvestmentStrategy | undefined)}
                >
                  <Select.Trigger placeholder="Any" variant="soft" className="w-full" />
                  <Select.Content>
                    {STRATEGY_OPTIONS.map((o) => (
                      <Select.Item key={o.value} value={o.value}>{o.label}</Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </div>
              <div>
                <FieldLabel>Vacancy Tolerance</FieldLabel>
                <Select.Root
                  value={criteria.vacancy_tolerance || ""}
                  onValueChange={(v) => updateCriteria("vacancy_tolerance", (v || undefined) as VacancyTolerance | undefined)}
                >
                  <Select.Trigger placeholder="Any" variant="soft" className="w-full" />
                  <Select.Content>
                    {VACANCY_OPTIONS.map((o) => (
                      <Select.Item key={o.value} value={o.value}>{o.label}</Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </div>
            </div>
          </Section>

          {/* ── Timing & Priority ── */}
          <Section icon={<Clock size={16} />} title="Timing & Priority">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <FieldLabel>Priority</FieldLabel>
                <Select.Root
                  value={criteria.priority || ""}
                  onValueChange={(v) => updateCriteria("priority", (v || undefined) as MandatePriority | undefined)}
                >
                  <Select.Trigger placeholder="Primary" variant="soft" className="w-full" />
                  <Select.Content>
                    {PRIORITY_OPTIONS.map((o) => (
                      <Select.Item key={o.value} value={o.value}>{o.label}</Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </div>
              <div>
                <FieldLabel>Timeline</FieldLabel>
                <Select.Root
                  value={criteria.timeline || ""}
                  onValueChange={(v) => updateCriteria("timeline", (v || undefined) as MandateTimeline | undefined)}
                >
                  <Select.Trigger placeholder="Immediate" variant="soft" className="w-full" />
                  <Select.Content>
                    {TIMELINE_OPTIONS.map((o) => (
                      <Select.Item key={o.value} value={o.value}>{o.label}</Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </div>
            </div>
          </Section>

          {/* ── Notes ── */}
          <Section icon={<Notepad size={16} />} title="Notes">
            <TextArea
              size="2"
              rows={4}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Qualitative context — what else matters to this buyer?"
            />
          </Section>
        </div>

        {/* Fixed footer */}
        <div
          className="flex items-center justify-end gap-2 px-5 py-4 border-t shrink-0"
          style={{ borderColor: "var(--gray-4)" }}
        >
          <Button variant="soft" color="gray" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving
              ? isEditMode
                ? "Saving..."
                : "Creating..."
              : isEditMode
                ? "Save Changes"
                : "Create Mandate"}
          </Button>
        </div>
      </div>
    </>
  );
}
