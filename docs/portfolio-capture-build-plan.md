# Portfolio Capture — Build Plan

## Purpose

A Cleo feature: paste an owner's website URL, and Cleo extracts their portfolio, company details, and people, lets the user review, and commits it so ownership is accurate for buyer/seller prospecting. A match-key engine then attaches dark GW/RT properties to the right owner automatically.

The problem it solves: Cleo builds ownership from Realtrack transactions, so deep-held assets that never traded come through "dark" with no owner, and owners fragment across name-variant groups. Owner websites publicly prove "this group owns/manages these properties." Capturing that fills the gap.

## Principles (non-negotiable)

1. **Cleo is the source of truth for assets.** HubSpot holds the relationship plus a rollup. No double hand-entry.
2. **All captured data persists in CRM/persistent tables, never derived tables.** The compiler rebuilds `properties`, `groups`, etc. from clean-data; captured data must survive that.
3. **Provenance on everything.** Each field tagged source + confidence + `web_asserted` vs `registry_confirmed`. Registry/GW confirmations outrank web. Re-capture refreshes web fields but never clobbers a confirmed one.
4. **Human review before commit.** Websites omit and mislead; owns-vs-manages is a judgment call. Nothing writes to Cleo without a human yes.

## Pipeline

1. **Input:** a URL (site root or portfolio page).
2. **Crawl** (Playwright, already in the stack for the Ontario geocoder): discover portfolio/property/about/management/contact pages and PDFs; render JS where needed.
3. **Extract** (Claude API, structured output to the schema below).
4. **Resolve & dedup:** each property address → existing parcel resolver → ARN → match against existing Cleo properties; resolve the group against existing groups via match-keys (catches the fragmented variants).
5. **Stage + review** (React UI): owner block, property rows, and match-suggestions. User edits, sets owns/manages, approves or drops items.
6. **Commit:** write to the persistent tables.
7. **Match-key sweep:** scan GW/RT data for dark or mis-owned properties hitting the group's signals; surface for one-click attach.

## Data model (new / extended — all in the persistent CRM category)

- **group_profile** — group_id, canonical_name, summary, business_lines[], corp_address, corp_phone, fax, domain, website, socials[], source_url, captured_at, confidence.
- **group_aliases** — group_id, alias (name variants; feeds dedup + merge).
- **group_match_keys** — group_id, key_type (address | phone | domain | alias | person | spv_name), value, source. Drives the attach engine.
- **manual_owner_links** — arn/property_id, group_id, relationship (owns | manages | lists), source, confidence, captured_at. Applied by the reader/compiler as an override on top of derived data; survives rebuild.
- **property_capture** (extends property_enrichment) — arn/property_id, property_name, retail_subtype, total_sqft, units, parking, floors, acreage, vacancy, asking_rate, pdf_links[], source_url, captured_at, confidence.
- **property_tenants** — property_id, unit, tenant_name, sqft, is_anchor, source.
- **group_contacts / people** (exists) — name, title, email, phone, source, confidence.
- **manual_properties** — for assets listed on a site but not yet in Cleo (no RT/GW); minimal record, resolved to ARN.

## Extraction protocol (the durable artifact)

GROUP: canonical_name; aliases[]; summary; business_lines[] (owner/developer/property_manager/brokerage); corp_address; corp_phone; fax; emails[] + domain; website; socials[]; partners[]; people[] {name,title,email,phone}.

PROPERTIES[]: name; street_address; city; province; postal; property_type; retail_subtype; anchor_tenant; tenants[] {name,sqft}; total_sqft; units; parking; floors; acreage; vacancy_or_available; asking_rate; relationship (owns/manages/lists/unclear + reasoning); pdf_links[]; source_url.

META: site_structure_notes; data_quality_notes (gaps, ambiguities, owns-vs-manages confidence).

Rule: unknown fields are explicitly null, never guessed.

## Match-key engine

On commit, store the group's match-keys. A matcher scans `transaction_mailing_addresses`, `transaction_parties`, and `gw_assessments` for hits — same mailing address, an alias entity, an ATTN/principal name, a shared phone, or a known SPV name. Each hit becomes a one-click "attach to this group" candidate that writes a `manual_owner_link`.

Proven on real data during the test runs:
- Strongman's "King Rose LP" = the dark Metro at 1900 King St E, Hamilton (GW owner "King Rose G.P. Inc," mailing 1885 Marine Dr = Strongman's office).
- Biddington's Fennell Plaza = the dark Metro at 969 Fennell Ave E, Hamilton (GW owner "Kilbarry Holding Corp," mailing 1962 Yonge St Ste 200 = Biddington's HQ).

## UI (in-app, no CLI)

- **Capture Portfolio** page: URL input → progress → review screen (owner + properties + flagged items) → Approve.
- **Match-suggestions** panel after commit (attach the dark hits).
- **Owner page**: shows captured portfolio with provenance badges (web-asserted vs confirmed).

## Compiler safety

`manual_owner_links`, `group_profile`, `property_capture`, `property_tenants` are persistent CRM tables. The reader applies them as overrides; `drop_derived_tables()` never touches them. This is the make-or-break requirement.

## Phasing

- **v1:** crawl + extract + review + commit (group_profile, aliases, match-keys, manual_owner_links, property_capture, tenants), group merge for dedup, match-key sweep on address/alias/phone/SPV.
- **v2:** PDF site-plan parsing for GLA/units; contact enrichment as a separate downstream step (email-pattern, Apollo/ZoomInfo/Clay, RECO, GW ATTN names); scheduled re-capture; conflict-resolution UI.

## First run (verified seed data)

- **Rosart Properties Inc** — Oakville, 226 South Service Rd E. 10 properties incl. FreshCo-anchored Stadium Mall (869 Barton St E) and Strathbarton Mall (1565 Barton St E), Maple Mews (LCBO/Dollarama/Beer Store), Guelph Line (Samir Supermarket). Owns/self-manages. Merge the 3 fragmented Cleo groups (GRP_50676, GRP_113166, GRP_114559) into one.
- **The Strongman Group** — North Vancouver, 1885 Marine Dr. ~48 properties across BC/AB/SK/ON; owner SPVs exposed (Gerry Strongman Holdings, King Rose LP, Redline Inv Prop LP, Fort Plaza Ltd, DRSSL Ltd). Owns/self-manages. Attach dark Metro 1900 King St E Hamilton.
- **The Biddington Group** — Toronto, 1962 Yonge St Ste 200. Commercial/industrial/residential incl. Fennell Plaza (969-1007 Fennell E Hamilton), Downsview/Warden/Westown/Markham Plazas. Owns/manages; JV homebuilder (Mattamy, Monarch). Attach dark Metro 969 Fennell Hamilton.
