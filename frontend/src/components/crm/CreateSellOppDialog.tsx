/**
 * CreateSellOppDialog — create a sell opportunity from a property page.
 *
 * Derivation chain:
 *   NOI + Cap Rate → Expected Price
 *   Expected Price × Commission % → Deal Value
 *
 * Each output can be manually overridden. Inputs drive derivatives
 * only when the user hasn't typed into the output field.
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Heading, Text, TextField, TextArea } from "@radix-ui/themes";
import { X } from "@phosphor-icons/react";
import { postApi } from "../../api/client";
import { formatCurrency } from "../../lib/utils";

interface CreateSellOppDialogProps {
  propertyId: string;
  propertyAddress: string;
  onClose: () => void;
}

export default function CreateSellOppDialog({
  propertyId,
  propertyAddress,
  onClose,
}: CreateSellOppDialogProps) {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);

  // Raw string inputs (what the user typed)
  const [noiStr, setNoiStr] = useState("");
  const [capRateStr, setCapRateStr] = useState("");
  const [expectedPriceStr, setExpectedPriceStr] = useState("");
  const [commissionStr, setCommissionStr] = useState("");
  const [dealValueStr, setDealValueStr] = useState("");
  const [notes, setNotes] = useState("");

  // Track whether user has manually edited derived fields
  const [priceManual, setPriceManual] = useState(false);
  const [dealValueManual, setDealValueManual] = useState(false);

  // Parse helpers
  const parseNum = (s: string) => { const n = parseFloat(s); return isNaN(n) ? null : n; };
  const parseIntNum = (s: string) => { const n = parseInt(s); return isNaN(n) ? null : n; };

  // Derived values
  const noi = parseIntNum(noiStr);
  const capRate = parseNum(capRateStr);
  const commission = parseNum(commissionStr);

  // Compute expected price from NOI + cap rate (if not manually set)
  const computedPrice = noi && capRate && capRate > 0 ? Math.round(noi / (capRate / 100)) : null;
  const expectedPrice = priceManual ? parseIntNum(expectedPriceStr) : (computedPrice ?? parseIntNum(expectedPriceStr));

  // Compute deal value from expected price + commission (if not manually set)
  const computedDealValue = expectedPrice && commission ? Math.round(expectedPrice * (commission / 100)) : null;
  const dealValue = dealValueManual ? parseIntNum(dealValueStr) : (computedDealValue ?? parseIntNum(dealValueStr));

  // Sync computed values into the text fields (for display)
  useEffect(() => {
    if (!priceManual && computedPrice !== null) {
      setExpectedPriceStr(String(computedPrice));
    }
  }, [computedPrice, priceManual]);

  useEffect(() => {
    if (!dealValueManual && computedDealValue !== null) {
      setDealValueStr(String(computedDealValue));
    }
  }, [computedDealValue, dealValueManual]);

  async function handleCreate() {
    setSaving(true);
    try {
      const result = await postApi<{ id: string }>("/sell-opportunities", {
        property_id: propertyId,
        noi: noi || null,
        expected_cap_rate: capRate ? capRate / 100 : null,
        expected_price: expectedPrice || null,
        commission_pct: commission ? commission / 100 : null,
        deal_value: dealValue || null,
        notes: notes || null,
      });
      navigate(`/opportunities/sell/${result.id}`);
    } catch {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div
        className="relative bg-white rounded-xl border border-[var(--gray-6)] shadow-xl w-full max-w-lg p-6 mx-4"
        style={{ backgroundColor: "var(--color-background)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <Heading size="4">Create Sell Opportunity</Heading>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--gray-3)] transition-colors"
          >
            <X size={18} style={{ color: "var(--gray-9)" }} />
          </button>
        </div>

        <Text size="2" className="block mb-5" style={{ color: "var(--gray-11)" }}>
          {propertyAddress}
        </Text>

        <div className="space-y-4">
          {/* Row 1: NOI + Cap Rate → Expected Price */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
                NOI
              </Text>
              <TextField.Root
                value={noiStr}
                onChange={(e) => {
                  setNoiStr(e.target.value);
                  setPriceManual(false);
                  setDealValueManual(false);
                }}
                placeholder="e.g. 250000"
                type="number"
              />
            </div>
            <div>
              <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
                Expected Cap Rate (%)
              </Text>
              <TextField.Root
                value={capRateStr}
                onChange={(e) => {
                  setCapRateStr(e.target.value);
                  setPriceManual(false);
                  setDealValueManual(false);
                }}
                placeholder="e.g. 6.5"
                type="number"
              />
            </div>
          </div>

          {/* Expected Price (derived or manual) */}
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Text size="2" weight="medium" style={{ color: "var(--gray-11)" }}>
                Expected Price
              </Text>
              {!priceManual && computedPrice !== null && (
                <Text size="1" style={{ color: "var(--jade-11)" }}>
                  = NOI ÷ Cap Rate
                </Text>
              )}
            </div>
            <TextField.Root
              value={expectedPriceStr}
              onChange={(e) => {
                setExpectedPriceStr(e.target.value);
                setPriceManual(true);
                setDealValueManual(false);
              }}
              placeholder="e.g. 5000000"
              type="number"
            />
          </div>

          {/* Row 2: Commission % → Deal Value */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
                Commission (%)
              </Text>
              <TextField.Root
                value={commissionStr}
                onChange={(e) => {
                  setCommissionStr(e.target.value);
                  setDealValueManual(false);
                }}
                placeholder="e.g. 2.5"
                type="number"
              />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Text size="2" weight="medium" style={{ color: "var(--gray-11)" }}>
                  Deal Value
                </Text>
                {!dealValueManual && computedDealValue !== null && (
                  <Text size="1" style={{ color: "var(--jade-11)" }}>
                    = Price × Commission
                  </Text>
                )}
              </div>
              <TextField.Root
                value={dealValueStr}
                onChange={(e) => {
                  setDealValueStr(e.target.value);
                  setDealValueManual(true);
                }}
                placeholder="e.g. 125000"
                type="number"
              />
            </div>
          </div>

          {/* Summary line */}
          {(expectedPrice || dealValue) && (
            <div className="rounded-lg p-3" style={{ backgroundColor: "var(--jade-2)", border: "1px solid var(--jade-6)" }}>
              <div className="flex justify-between text-sm">
                {expectedPrice && (
                  <span style={{ color: "var(--gray-11)" }}>
                    Expected: <strong style={{ color: "var(--gray-12)" }}>{formatCurrency(expectedPrice)}</strong>
                  </span>
                )}
                {dealValue && (
                  <span style={{ color: "var(--gray-11)" }}>
                    Commission: <strong style={{ color: "var(--jade-11)" }}>{formatCurrency(dealValue)}</strong>
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Notes */}
          <div>
            <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
              Notes
            </Text>
            <TextArea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any notes about this opportunity..."
              rows={2}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="soft" color="gray" onClick={onClose}>Cancel</Button>
          <Button onClick={handleCreate} disabled={saving}>
            {saving ? "Creating..." : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}
