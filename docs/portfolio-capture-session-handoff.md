# Portfolio Capture — New Session Handoff Prompt

Paste the block below into a fresh Claude Cowork session (with the cleo-turbo folder connected) to build the feature. Full spec lives in `docs/portfolio-capture-build-plan.md`.

---

Build the "Portfolio Capture" feature in my Cleo Turbo app.

Work in the cleo-turbo repo (the folder I've connected). Before anything, read `CLAUDE.md` (working rules and architecture) and `docs/portfolio-capture-build-plan.md` — that's the full spec for this feature. Follow the build plan; this prompt is the summary and the guardrails.

**What it does, in one line:** I paste an owner's website URL, Cleo crawls and extracts their portfolio, company, and people, I review and approve, and it commits to Cleo's persistent layer so ownership is accurate for buyer/seller prospecting. A match-key engine then attaches dark GeoWarehouse/Realtrack properties to the right owner.

**Hard constraints — do not violate:**

- Captured data lives only in persistent CRM-category tables, never the derived tables. The compiler's `drop_derived_tables()` must never touch them. Confirm your new tables are excluded from that drop list, and prove with a test that captured data survives a full compiler rebuild.
- I do not use a CLI. Every capability needs a UI surface in the React app. Internal test scripts are fine, but anything I use has to be in the app.
- This touches the schema and pipeline, so per CLAUDE.md, explain your plan and get my approval before writing the migration or code. Work on a git branch. Test the migration and the read-path against a copy of `data/cleo.db`, never the live file.
- Ports are fixed: backend 8099, frontend 5174. Use the cleo-turbo-frontend skill for UI work.

**Ownership-override policy (already decided):** a captured "owns" link fills blank or dark properties automatically. Where it conflicts with a Realtrack-derived owner, it must NOT overwrite — flag the conflict for review instead.

**Build in milestones, get my sign-off between each:**

1. Persistence + override read-path: new tables (`group_profile`, `group_aliases`, `group_match_keys`, `manual_owner_links`, `property_capture`, `property_tenants`), the migration, and the reader override per the policy above. Test that a captured owner survives a rebuild.
2. Extraction pipeline: a backend endpoint that takes a URL, crawls it (Playwright is already in the stack), and runs a Claude API extraction against the schema and protocol in the build plan — strict JSON, nulls never guesses, and an owns/manages/lists judgment. Resolve each address through the existing parcel resolver to an ARN and dedup against existing properties.
3. Review UI: a "Capture Portfolio" page — paste URL, see the staged owner plus property rows plus flagged items, edit, set owns/manages, Approve. Then a match-suggestions panel.
4. Match-key engine: on commit, store the group's match-keys, then sweep `transaction_mailing_addresses`, `transaction_parties`, and `gw_assessments` for hits and surface attach candidates.

**First real run, and the acceptance tests, use these three sites:**

- `https://www.rosartproperties.com/` — captures 10 properties with tenant rosters; merges the three fragmented "Rosart Properties Inc" groups in Cleo into one; Stadium Mall (869 Barton St E, Hamilton) and Strathbarton Mall (1565 Barton St E) show FreshCo anchors; owns/self-manages.
- `https://www.thestrongmangroup.com/properties/` — ~48 properties listed by address and owner SPV. Match-key test: their "King Rose LP" must link to the dark Metro at 1900 King St E, Hamilton (GW owner "King Rose G.P. Inc," mailing 1885 Marine Dr, which is Strongman's office).
- `https://biddington.com/lease-commercial.php` — a lease-listing site, so the owns-vs-manages judgment is the real test; it should resolve to owns/manages, not third-party brokerage. Match-key test: their "Fennell Plaza" (969-1007 Fennell Ave E, Hamilton) must link to the dark Metro at 969 Fennell (GW owner "Kilbarry Holding Corp," mailing 1962 Yonge St Ste 200, which is Biddington's head office).

**Provenance rule:** tag every captured field with source, confidence, and web-asserted vs registry-confirmed. Registry/GW outranks web; a web capture never overwrites a confirmed owner.

**Out of scope for v1 (note for later):** PDF site-plan parsing, contact enrichment as a separate downstream step (Apollo/ZoomInfo/RECO/email-pattern), and scheduled re-capture.

Start by reading `CLAUDE.md` and `docs/portfolio-capture-build-plan.md`, then propose your Milestone 1 plan for approval before writing any code.
