const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType,
  PageNumber, PageBreak,
} = require("docx");

// ── Helpers ──────────────────────────────────────────────────

function heading(text, level = HeadingLevel.HEADING_1) {
  return new Paragraph({ heading: level, children: [new TextRun(text)] });
}

function para(children, opts = {}) {
  const runs = typeof children === "string"
    ? [new TextRun(children)]
    : children;
  return new Paragraph({ children: runs, ...opts });
}

function bold(text) { return new TextRun({ text, bold: true }); }
function text(t) { return new TextRun(t); }
function ital(t) { return new TextRun({ text: t, italics: true }); }

function spacer() {
  return new Paragraph({ children: [], spacing: { after: 80 } });
}

// Callout box — a single-cell table with shaded background
function callout(title, bodyLines) {
  const border = { style: BorderStyle.SINGLE, size: 1, color: "B8D4E3" };
  const borders = { top: border, bottom: border, left: border, right: border };
  const children = [
    new Paragraph({ children: [new TextRun({ text: title, bold: true, size: 22 })], spacing: { after: 80 } }),
    ...bodyLines.map(line =>
      new Paragraph({
        children: typeof line === "string" ? [new TextRun({ text: line, size: 22 })] : line.map(r => {
          if (typeof r === "string") return new TextRun({ text: r, size: 22 });
          return new TextRun({ ...r, size: 22 });
        }),
        spacing: { after: 60 },
      })
    ),
  ];
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({
      children: [new TableCell({
        borders,
        shading: { fill: "E8F4F8", type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 200, right: 200 },
        width: { size: 9360, type: WidthType.DXA },
        children,
      })],
    })],
  });
}

// Table helper
function dataTable(headers, rows, colWidths) {
  const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
  const borders = { top: border, bottom: border, left: border, right: border };

  const headerRow = new TableRow({
    children: headers.map((h, i) => new TableCell({
      borders,
      shading: { fill: "F0F4F8", type: ShadingType.CLEAR },
      margins: { top: 60, bottom: 60, left: 100, right: 100 },
      width: { size: colWidths[i], type: WidthType.DXA },
      children: [new Paragraph({ children: [new TextRun({ text: h, bold: true, size: 20, font: "Arial" })] })],
    })),
  });

  const dataRows = rows.map(row => new TableRow({
    children: row.map((cell, i) => new TableCell({
      borders,
      margins: { top: 40, bottom: 40, left: 100, right: 100 },
      width: { size: colWidths[i], type: WidthType.DXA },
      children: [new Paragraph({
        children: typeof cell === "string"
          ? [new TextRun({ text: cell, size: 20, font: "Arial" })]
          : cell.map(r => typeof r === "string" ? new TextRun({ text: r, size: 20, font: "Arial" }) : new TextRun({ ...r, size: 20, font: "Arial" })),
      })],
    })),
  }));

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [headerRow, ...dataRows],
  });
}

// Bullet list
const bulletConfig = {
  reference: "bullets",
  levels: [{
    level: 0, format: LevelFormat.BULLET, text: "\u2022",
    alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 720, hanging: 360 } } },
  }],
};

function bullet(children) {
  const runs = typeof children === "string"
    ? [new TextRun(children)]
    : children;
  return new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: runs });
}

// ── Document ─────────────────────────────────────────────────

const doc = new Document({
  numbering: { config: [bulletConfig] },
  styles: {
    default: { document: { run: { font: "Arial", size: 24 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 },
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          children: [new TextRun({ text: "CLEO TURBO \u2014 Phase 2.5: Group Merging", size: 18, color: "888888", font: "Arial" })],
          alignment: AlignmentType.RIGHT,
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          children: [new TextRun({ text: "Page ", size: 18, color: "888888" }), new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "888888" })],
          alignment: AlignmentType.CENTER,
        })],
      }),
    },
    children: [
      // ── Title ──
      para([bold("CLEO TURBO")], { alignment: AlignmentType.CENTER, spacing: { after: 40 } }),
      para([bold("Phase 2.5: Group Merging")], { alignment: AlignmentType.CENTER, spacing: { after: 40 } }),
      para([text("Implementation Plan")], { alignment: AlignmentType.CENTER, spacing: { after: 80 } }),
      para([text("April 2026")], { alignment: AlignmentType.CENTER, spacing: { after: 80 } }),
      para([ital("Consolidate duplicate groups into single entities with merged portfolios, contacts, and transaction history \u2014 permanently and compiler-safe.")], {
        alignment: AlignmentType.CENTER, spacing: { after: 400 },
      }),

      // ── 1. The Problem ──
      heading("1. The Problem", HeadingLevel.HEADING_1),

      para("The reconciler assigns group IDs (GRP_NNNNN) based on normalized company names. When a company appears in Realtrack transactions under different legal name variants, each variant gets its own group. The result: a single real-world entity is fractured across multiple groups, splitting its portfolio, contacts, and transaction history."),
      spacer(),

      para([bold("Skyline Real Estate")], { spacing: { after: 80 } }),
      para("Skyline appears as 54 separate groups in Cleo. The main entity has 104 properties and 212 transactions, but their commercial arm (21 props, 58 txns), retail arm (30 props, 53 txns), and various SPVs are all separate. A merged view would show ~220+ properties and 400+ transactions \u2014 a dramatically different picture of the portfolio."),
      spacer(),

      para([bold("CAPREIT Apartments")], { spacing: { after: 80 } }),
      para([text("9 groups, 3 of which are typos: "), ital("CAPREIT Apratments"), text(", "), ital("CAPREIT Aprtments"), text(", "), ital("CAPREIT Apartmnents"), text(". These should obviously be one group.")]),
      spacer(),

      para([bold("Loblaw Properties")], { spacing: { after: 80 } }),
      para([text("8 groups including a typo ("), ital("Loblaw Propseties"), text(") and a phone number appended to the name ("), ital("Loblaw Properties Ltd     416-922-500"), text(").")]),
      spacer(),

      para([bold("RioCan Holdings")], { spacing: { after: 80 } }),
      para("26 groups. Many are legitimate SPVs (RioCan Holdings (Collingwood) Inc), but the top-level entity is split between RioCan Holdings Inc (45 props, 121 txns) and RioCan PS Inc (4 props, 19 txns). A CRE prospector needs to see the full RioCan picture in one place."),
      spacer(),

      para("This isn\u2019t just cosmetic. When Brandon is prospecting, he needs to see a group\u2019s full portfolio on the map, their real transaction velocity, their true geographic footprint. Split groups hide the signal."),

      // ── 2. Design Principles ──
      heading("2. Design Principles", HeadingLevel.HEADING_1),

      bullet([bold("Manual merges only."), text(" The system suggests nothing automatically. Brandon decides which groups are the same entity and executes the merge. This avoids false positives \u2014 not every \u201CSkyline\u201D is the same Skyline.")]),
      bullet([bold("Compiler-safe."), text(" Merges persist across compiler rebuilds. When the compiler recreates groups from clean-data, it checks the merge table and redirects absorbed groups to their merge target.")]),
      bullet([bold("Reversible."), text(" Merges can be undone. An unmerge restores the original groups, returning properties, contacts, and transactions to their original owners. This is a safety net, not a common operation.")]),
      bullet([bold("CRM data follows."), text(" Notes, list memberships, deals, and any manual contact links on the absorbed group move to the surviving group. Nothing is lost.")]),
      bullet([bold("Audit trail."), text(" Every merge is logged with who did it and when. The merge history is visible on the group detail page.")]),

      // ── 3. Data Model ──
      heading("3. Data Model", HeadingLevel.HEADING_1),

      heading("3a. New Table: group_merges", HeadingLevel.HEADING_2),
      para("A CRM-layer table (never touched by the compiler) that records which groups have been merged into which."),
      spacer(),

      dataTable(
        ["Column", "Type", "Description"],
        [
          ["id", "INTEGER PK", "Autoincrement"],
          ["source_group_id", "TEXT FK", "The group being absorbed (goes away)"],
          ["target_group_id", "TEXT FK", "The surviving group (receives everything)"],
          ["merged_by", "TEXT", "Username of who performed the merge"],
          ["merged_at", "TEXT", "Timestamp of merge"],
          ["unmerged_at", "TEXT", "Timestamp of unmerge (NULL if still merged)"],
          ["unmerged_by", "TEXT", "Username of who unmerged (NULL if still merged)"],
        ],
        [2000, 1800, 5560],
      ),
      spacer(),

      callout("Why not just delete the absorbed group?", [
        "The compiler will recreate it on the next rebuild from clean-data. We need the group to exist so the compiler can find it and redirect it. The absorbed group stays in the groups table with status='merged' and is hidden from all browse/search results.",
      ]),
      spacer(),

      heading("3b. Reconciler Changes", HeadingLevel.HEADING_2),
      para("The reconciler\u2019s get_or_create_group_id() method stays unchanged \u2014 it still assigns GRP_ IDs based on normalized names. The change happens in the writer, after groups are created."),
      spacer(),
      para("At the end of Pass 1 (Groups), before committing:"),
      spacer(),

      bullet("Load all active merges from group_merges (WHERE unmerged_at IS NULL)"),
      bullet("For each merge: find any properties, contacts, or transaction_parties that reference the source group and redirect them to the target group"),
      bullet("Update the source group\u2019s status to \u2018merged\u2019"),
      bullet("Copy any new known_names from the source group to the target group (preserving name history)"),
      spacer(),

      para("This means: after a compiler rebuild, the merged state is automatically restored. The merge is permanent until explicitly unmerged."),
      spacer(),

      callout("Critical: CRM tables are not touched by the compiler", [
        "The writer only redirects derived-table references (properties.current_owner_group_id, contacts.current_group_id, transaction_parties.group_id). CRM data (notes, deals, list members) was already moved during the original merge operation and lives in CRM tables that the compiler never rebuilds.",
      ]),

      // ── 4. Merge Operation ──
      heading("4. Merge Operation", HeadingLevel.HEADING_1),

      para("When Brandon merges Group B into Group A, the following steps execute in a single transaction:"),
      spacer(),

      heading("4a. Derived Tables (rebuilt by compiler)", HeadingLevel.HEADING_2),

      dataTable(
        ["Table", "Column", "Action"],
        [
          ["properties", "current_owner_group_id", "UPDATE SET target WHERE source"],
          ["contacts", "current_group_id", "UPDATE SET target WHERE source"],
          ["contacts", "company_name", "Optionally update to target\u2019s display_name"],
          ["transaction_parties", "group_id", "UPDATE SET target WHERE source"],
          ["group_names", "group_id", "Copy source\u2019s names to target (INSERT OR IGNORE)"],
          ["groups", "status", "SET \u2018merged\u2019 on source group"],
          ["groups", "property_count, etc.", "Recompute counts on target group"],
        ],
        [2200, 2800, 4360],
      ),
      spacer(),

      heading("4b. CRM Tables (persistent)", HeadingLevel.HEADING_2),

      dataTable(
        ["Table", "Column", "Action"],
        [
          ["group_notes", "group_id", "UPDATE SET target WHERE source"],
          ["group_contacts", "group_id", "UPDATE SET target WHERE source (skip duplicates)"],
          ["deals", "group_id", "UPDATE SET target WHERE source"],
          ["list_members", "member_id", "UPDATE WHERE member_type=\u2018group\u2019 AND member_id=source"],
        ],
        [2200, 2800, 4360],
      ),
      spacer(),

      heading("4c. Analytics", HeadingLevel.HEADING_2),
      para("After the merge, trigger a targeted analytics refresh for the target group. This recomputes portfolio value, transaction velocity, geographic radius, and property type mix based on the now-larger portfolio."),

      // ── 5. Unmerge Operation ──
      heading("5. Unmerge Operation", HeadingLevel.HEADING_1),

      para("Unmerging reverses the operation. Since the compiler tracks which normalized names map to which GRP_ IDs (via the reconciler), and clean-data still contains the original transactions, an unmerge is essentially:"),
      spacer(),

      bullet("Set unmerged_at and unmerged_by on the group_merges record"),
      bullet("Re-run the compiler (or trigger a targeted rebuild)"),
      bullet("The compiler, no longer seeing an active merge for this pair, will assign properties/contacts back to their original groups based on the clean-data"),
      spacer(),

      para("CRM data that was moved during the merge stays on the target group. This is intentional \u2014 notes written about the combined entity belong to whichever group the user considers the \u201Creal\u201D one. If specific notes need to move back, that\u2019s a manual operation."),

      // ── 6. Multi-Merge ──
      heading("6. Multi-Merge (Merging 3+ Groups)", HeadingLevel.HEADING_1),

      para("Skyline has 54 groups. Brandon won\u2019t want to merge them one at a time. The merge UI should support selecting multiple source groups and merging them all into a single target in one operation."),
      spacer(),
      para("Implementation: each source group gets its own row in group_merges pointing to the same target. The merge logic runs for each pair sequentially within the same transaction. If any step fails, the whole batch rolls back."),
      spacer(),
      para("The UI flow:"),
      spacer(),
      bullet([text("On the group detail page, click "), bold("Merge Groups")]),
      bullet("A modal opens with a search bar to find groups to merge in"),
      bullet("Selected groups appear in a list with their property count, transaction count, and display name"),
      bullet("Brandon picks which name should be the primary display name for the surviving group"),
      bullet([text("A preview shows the combined totals: "), ital("\u201CThis will create a group with 220 properties, 400 transactions, 12 contacts\u201D")]),
      bullet("Confirm and execute"),

      // ── 7. Suggested Merges ──
      heading("7. Suggested Merges (Discovery)", HeadingLevel.HEADING_1),

      para("Finding duplicates across 110,304 groups manually would be impractical. The system should surface likely duplicates without auto-merging them."),
      spacer(),

      heading("7a. Detection Strategies", HeadingLevel.HEADING_2),
      spacer(),

      bullet([bold("Prefix matching:"), text(" Groups where one normalized name is a prefix of another (e.g., \u201CSKYLINE REAL ESTATE\u201D starts with \u201CSKYLINE\u201D). High recall, moderate precision.")]),
      bullet([bold("Edit distance:"), text(" Groups with normalized names within Levenshtein distance 1\u20132 (catches typos like \u201CAPRATMENTS\u201D vs \u201CAPARTMENTS\u201D). High precision for typos.")]),
      bullet([bold("Shared property overlap:"), text(" Groups where both have been buyer/seller on the same properties. Very high precision but limited coverage.")]),
      spacer(),

      para("These run as batch queries and surface results on a dedicated \u201CMerge Suggestions\u201D page (or as a section in the Data Quality page that already exists). Each suggestion shows both groups side-by-side with their stats, and offers a one-click \u201CMerge\u201D button."),
      spacer(),

      callout("Not auto-merge", [
        "The system NEVER auto-merges. Not every \u201CSkyline\u201D is Skyline Real Estate. Not every \u201CSmith\u201D typo is the same Smith. Suggestions are just that \u2014 suggestions. Brandon reviews and confirms each one.",
      ]),

      // ── 8. API Endpoints ──
      heading("8. API Endpoints", HeadingLevel.HEADING_1),

      dataTable(
        ["Method", "Path", "Description"],
        [
          ["POST", "/api/groups/merge", "Execute a merge (body: { source_ids: [], target_id, primary_display_name })"],
          ["POST", "/api/groups/{id}/unmerge", "Reverse a merge (restores source group)"],
          ["GET", "/api/groups/{id}/merge-history", "List all merges involving this group"],
          ["GET", "/api/groups/merge-suggestions", "Get suggested duplicate groups"],
          ["GET", "/api/groups/{id}/merge-candidates", "Get likely duplicates for a specific group"],
        ],
        [1000, 3600, 4760],
      ),

      // ── 9. UI Changes ──
      heading("9. UI Changes", HeadingLevel.HEADING_1),

      heading("9a. Group Detail Page", HeadingLevel.HEADING_2),
      bullet([bold("Merge button"), text(" in the header, next to Notes and Promote. Opens the merge modal.")]),
      bullet([bold("Merge history card"), text(" showing past merges: \u201CMerged with Skyline Commercial Real Estate Holdings Inc on Apr 8, 2026 by Brandon\u201D")]),
      bullet([bold("Known Names section"), text(" now includes names from all merged groups (this already works via group_names, it just gets richer after merges)")]),
      spacer(),

      heading("9b. Groups Browse Page", HeadingLevel.HEADING_2),
      bullet([text("Groups with status="), ital("merged"), text(" are excluded from browse results (they still exist in the DB but are hidden)")]),
      bullet("Search still finds merged groups by name, but redirects to the target group"),
      spacer(),

      heading("9c. Merge Suggestions Page", HeadingLevel.HEADING_2),
      bullet("New page (or section in Data Quality) showing duplicate detection results"),
      bullet("Side-by-side comparison cards with property counts, transaction counts, portfolio value"),
      bullet("One-click merge with a confirmation modal"),
      bullet("Ability to dismiss a suggestion (\u201Cthese are not the same\u201D) so it doesn\u2019t keep showing up"),

      // ── 10. Edge Cases ──
      heading("10. Edge Cases", HeadingLevel.HEADING_1),

      heading("10a. SPVs and Subsidiaries", HeadingLevel.HEADING_2),
      para([text("RioCan Holdings (Collingwood) Inc is a legitimate SPV, not a duplicate. But Brandon might "), ital("want"), text(" to merge it into the RioCan parent anyway \u2014 for prospecting purposes, he cares about the whole RioCan portfolio, not the legal structure. The system should allow this without judgment. The known_names list preserves the SPV name for reference.")]),
      spacer(),

      heading("10b. Chain Merges", HeadingLevel.HEADING_2),
      para("If Group A was already merged into Group B, and now Brandon wants to merge Group C into Group A \u2014 the system should redirect to Group B (the ultimate target). The merge logic follows the chain: if target_group_id is itself a source in another merge, follow the chain to the final target."),
      spacer(),

      heading("10c. GW Watcher Incremental Updates", HeadingLevel.HEADING_2),
      para("The GW watcher does incremental DB updates (bypasses the compiler). It creates properties with current_owner_group_id. If the watcher assigns a property to a group that has been merged, it should check group_merges and redirect to the target. This requires a small lookup in the watcher\u2019s property insertion code."),
      spacer(),

      heading("10d. HubSpot Sync (Future)", HeadingLevel.HEADING_2),
      para("When Phase 6 (HubSpot Bridge) is built, merged groups should sync as a single Company to HubSpot. The merge table provides the mapping. If a merged group already had a hubspot_id, that Company record should be merged/archived in HubSpot too (or flagged for manual cleanup)."),

      // ── 11. Build Order ──
      heading("11. Build Order", HeadingLevel.HEADING_1),

      para([bold("Estimated duration: 2\u20133 days")]),
      para([bold("Risk: Low-Medium"), text(" \u2014 new tables and a compiler modification, but all existing data is preserved. Merges are reversible.")]),
      spacer(),

      heading("Step 1: Database & Backend (Day 1)", HeadingLevel.HEADING_2),
      bullet("Create group_merges table (migration)"),
      bullet("Build merge API endpoint (POST /api/groups/merge)"),
      bullet("Build unmerge API endpoint (POST /api/groups/{id}/unmerge)"),
      bullet("Build merge history endpoint (GET /api/groups/{id}/merge-history)"),
      bullet("Modify compiler writer Pass 1 to check group_merges and redirect references"),
      bullet("Test: merge two groups, run compiler, verify merge survives"),
      spacer(),

      heading("Step 2: Merge UI (Day 1\u20132)", HeadingLevel.HEADING_2),
      bullet("Merge modal component (search, select, preview, confirm)"),
      bullet("Add Merge button to GroupDetailPage header"),
      bullet("Merge history card on GroupDetailPage"),
      bullet("Hide merged groups from browse results"),
      bullet("Search redirect for merged group names"),
      spacer(),

      heading("Step 3: Merge Suggestions (Day 2\u20133)", HeadingLevel.HEADING_2),
      bullet("Build suggestion detection queries (prefix match + edit distance)"),
      bullet("Build merge-suggestions API endpoint"),
      bullet("Merge suggestions UI (page or Data Quality section)"),
      bullet("Dismiss suggestion functionality"),
      spacer(),

      heading("Step 4: Validation (Day 3)", HeadingLevel.HEADING_2),
      bullet("Merge the Skyline groups as a real-world test"),
      bullet("Verify portfolio map shows all Skyline properties"),
      bullet("Verify analytics (portfolio value, transaction velocity) reflect merged data"),
      bullet("Run compiler rebuild, verify merge persists"),
      bullet("Test unmerge, verify clean separation"),
      bullet("TypeScript check, no regressions"),

      // ── 12. What This Unlocks ──
      heading("12. What This Unlocks", HeadingLevel.HEADING_1),

      para("Group merging isn\u2019t just data cleanup. It\u2019s the difference between seeing Skyline as a 104-property regional player and seeing them as a 220+ property provincial portfolio. It transforms the mini-maps from partial snapshots into complete portfolio views. It makes the portfolio value column meaningful for major players. And it makes the filtering engine\u2019s results accurate \u2014 when Brandon filters for groups with 50+ properties, he should find the real answer, not an answer fractured across name variants."),
      spacer(),
      para("This is foundational work that makes every subsequent phase (Opportunities, Mandates, Matchmaking) more accurate from day one."),
    ],
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/sessions/kind-elegant-mendel/mnt/cleo-turbo/Phase-2.5-Group-Merging-Plan.docx", buffer);
  console.log("Done: Phase-2.5-Group-Merging-Plan.docx");
});
