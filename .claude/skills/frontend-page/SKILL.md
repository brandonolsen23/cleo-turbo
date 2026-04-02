---
name: frontend-page
description: |
  How to add a new page to the Cleo Turbo React frontend. Use this skill whenever the task involves creating a new page, adding a new route, building a new list/browse view, building a new detail view, or adding a new section to the sidebar navigation. Also use when modifying existing pages — the patterns here are the source of truth for how pages should be structured. Trigger on: "add a page", "new page", "create a view", "build a list page", "build a detail page", "add to sidebar", or any request that involves creating or significantly restructuring a frontend page component.
---

# Frontend Page Skill — Cleo Turbo

This skill covers the complete process of adding a new page to the Cleo Turbo frontend. It reflects the actual patterns used across 15+ existing pages as of the current codebase.

## The Checklist

Every new page touches these files, in this order:

1. `frontend/src/types/index.ts` — add TypeScript interfaces
2. `frontend/src/pages/YourPage.tsx` — create the page component
3. `frontend/src/App.tsx` — import and add the route
4. `frontend/src/components/layout/Sidebar.tsx` — add nav link (if top-level page)
5. `frontend/src/components/layout/Header.tsx` — add page title mapping
6. `frontend/src/components/layout/AppLayout.tsx` — add to FULL_BLEED_ROUTES (only if full-bleed)

## Step 1: Types in types/index.ts

All TypeScript interfaces go in `frontend/src/types/index.ts` — never inline in the page component. This is the single source of truth for API response shapes.

**Browse item interface** (what the list endpoint returns per row):
```typescript
export interface YourBrowseItem {
  id: string;
  name: string;
  // ... fields matching the API response
}
```

**Detail interface** (what the detail endpoint returns):
```typescript
export interface YourDetail {
  id: string;
  name: string;
  // ... all fields, including nested objects
  related_items: RelatedItem[];
}
```

The existing `BrowseResponse<T>` generic is already defined and should be reused:
```typescript
// Already exists — don't redefine
export interface BrowseResponse<T> {
  results: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}
```

## Step 2: Page Component

### Imports

Every page starts with the same import structure:

```typescript
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";        // browse pages
import { Link, useParams } from "react-router-dom";     // detail pages
import { Heading, Text, Badge, Button } from "@radix-ui/themes";
import { SomeIcon } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate, formatPhone } from "../lib/utils";
import type { YourBrowseItem, BrowseResponse } from "../types";
```

Key rules:
- Radix components for all UI primitives (`Heading`, `Text`, `Badge`, `Button`, `Tabs`, `DataList`, `Separator`, `Callout`)
- Phosphor icons from `@phosphor-icons/react` — never Heroicons, Lucide, or raw SVGs
- API helpers from `../api/client` — `fetchApi` for GET, `postApi` for POST, `mutateApi` for PUT/PATCH/DELETE
- Formatting helpers from `../lib/utils` — always use these, never format inline
- Types from `../types` — never define interfaces inline

### Browse Page Pattern

Browse pages follow this structure consistently. Use a native HTML `<table>` — the project does not use TanStack Table for list views.

```typescript
export default function YourPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseResponse<YourBrowseItem> | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    fetchApi<BrowseResponse<YourBrowseItem>>("/your-resource", {
      page: String(page),
      per_page: "25",
    }).then(setData);
  }, [page]);

  if (!data) {
    return (
      <div className="flex items-center justify-center h-64">
        <Text size="3" style={{ color: "var(--gray-9)" }}>Loading...</Text>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Heading size="6" weight="medium">Your Resource</Heading>
          <Badge size="1" variant="outline" color="gray">{data.total}</Badge>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-[var(--gray-2)] border-b border-[var(--gray-5)]">
              <th className="text-left text-[12px] font-medium px-4 py-2" style={{ color: "var(--gray-9)" }}>
                Column Header
              </th>
              {/* ... more columns */}
            </tr>
          </thead>
          <tbody>
            {data.results.map((item) => (
              <tr
                key={item.id}
                onClick={() => navigate(`/your-resource/${item.id}`)}
                className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer transition-colors"
              >
                <td className="px-4 py-3">
                  <Text size="2">{item.name}</Text>
                </td>
                {/* ... more cells */}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-4">
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          Page {data.page} of {data.pages} ({data.total} total)
        </Text>
        <div className="flex gap-2">
          <Button size="1" variant="soft" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
            Previous
          </Button>
          <Button size="1" variant="soft" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)}>
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
```

**Adding search** — if the page needs a search bar, add a dual-mode pattern where search results replace browse results:
```typescript
const [search, setSearch] = useState("");
const [searchResults, setSearchResults] = useState<SearchResponse<YourBrowseItem> | null>(null);

const doSearch = () => {
  if (!search.trim()) { setSearchResults(null); return; }
  fetchApi<SearchResponse<YourBrowseItem>>("/your-resource/search", {
    q: search, limit: "50",
  }).then(setSearchResults);
};

// Render searchResults.results if searchResults is set, otherwise data.results
```

**Adding filters** — use optional query params that map to backend WHERE conditions:
```typescript
const [categoryFilter, setCategoryFilter] = useState("");

useEffect(() => {
  const params: Record<string, string> = { page: String(page), per_page: "25" };
  if (categoryFilter) params.category = categoryFilter;
  fetchApi<BrowseResponse<YourBrowseItem>>("/your-resource", params).then(setData);
}, [page, categoryFilter]);
```

### Detail Page Pattern

Detail pages fetch a single entity by ID and display it in a card-based layout:

```typescript
export default function YourDetailPage() {
  const { id } = useParams();
  const [item, setItem] = useState<YourDetail | null>(null);

  useEffect(() => {
    if (id) fetchApi<YourDetail>(`/your-resource/${id}`).then(setItem);
  }, [id]);

  if (!item) {
    return (
      <div className="flex items-center justify-center h-64">
        <Text size="3" style={{ color: "var(--gray-9)" }}>Loading...</Text>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Back link */}
      <Link to="/your-resource" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
        &larr; Your Resource
      </Link>

      {/* Title area */}
      <Heading size="6" weight="bold">{item.name}</Heading>

      {/* Key stats in card grid */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Label</Text>
          <Text size="5" weight="bold" className="block mt-1">{item.value}</Text>
        </div>
        {/* ... more stat cards */}
      </div>

      {/* Content cards */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        {/* Card content */}
      </div>

      {/* Related data table (same table pattern as browse pages) */}
    </div>
  );
}
```

**Hooks must come before any early returns.** If you use `useMemo`, `useCallback`, or any other hook, it must be placed before the `if (!item) return` loading check. React requires hooks to run in the same order every render.

### Mutation Pattern

For pages with create/edit/delete:
```typescript
// Create
const handleCreate = async () => {
  await postApi("/your-resource", { name, description });
  loadData(); // re-fetch the list
};

// Update
const handleUpdate = async () => {
  await mutateApi(`/your-resource/${id}`, "PATCH", updates);
  loadData(); // re-fetch the detail
};

// Delete
const handleDelete = async () => {
  await mutateApi(`/your-resource/${id}`, "DELETE");
  navigate("/your-resource"); // go back to list
};
```

## Step 3: Route in App.tsx

Add the import and route in `frontend/src/App.tsx`:

```typescript
// Direct import for most pages
import YourPage from "./pages/YourPage";
import YourDetailPage from "./pages/YourDetailPage";

// Lazy import ONLY for heavy pages (maps, complex visualizations)
const YourHeavyPage = lazy(() => import("./pages/YourHeavyPage"));
```

Add routes inside the `<Route element={<AppLayout />}>` block:
```tsx
<Route path="/your-resource" element={<YourPage />} />
<Route path="/your-resource/:id" element={<YourDetailPage />} />
```

**Lazy loading criteria:** Only use `lazy()` for pages that import heavy libraries like Mapbox GL, large charting libraries, or complex visualization code. Standard CRUD pages should use direct imports.

## Step 4: Sidebar Navigation

In `frontend/src/components/layout/Sidebar.tsx`, add to the appropriate nav group:

```typescript
import { YourIcon } from "@phosphor-icons/react";

// Add to the appropriate group in NAV_GROUPS:
{ path: "/your-resource", label: "Your Resource", icon: YourIcon },
```

Nav groups are: unlabeled (main data), "CRM", "Pipeline", "System". Choose the one that fits.

## Step 5: Header Title

In `frontend/src/components/layout/Header.tsx`, add to `PAGE_TITLES`:

```typescript
const PAGE_TITLES: Record<string, string> = {
  // ... existing entries
  "/your-resource": "Your Resource",
};
```

For detail pages, add to the `getPageTitle` function:
```typescript
if (pathname.startsWith("/your-resource/")) return "Your Resource Detail";
```

## Step 6: Full-Bleed (Rare)

Only needed for pages like maps that need the entire viewport. In `AppLayout.tsx`, add the path to `FULL_BLEED_ROUTES`.

## Design System Reference

### Colors
- CSS variables: `var(--jade-9)`, `var(--gray-11)`, etc.
- Accent color is jade, gray is slate
- Muted text: `style={{ color: "var(--gray-9)" }}`
- Links: `style={{ color: "var(--accent-11)" }}` with `no-underline` class

### Card Pattern
```
className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5"
```

### Table Header
```
className="bg-[var(--gray-2)]"
// Header text:
className="text-[12px] font-medium" style={{ color: "var(--gray-9)" }}
```

### Status Badges
Always use Radix Badge — never raw HTML spans with Tailwind colors:
```tsx
<Badge size="1" variant="soft" color={status === "engaged" ? "jade" : "gray"}>
  {status}
</Badge>
```

### Currency
Always CAD, always via `formatCurrency()` from `lib/utils.ts`.

### Ports
- Frontend: **5174** (configured in vite.config.ts, strictPort)
- Backend: **8099**

## What NOT to Do

- Don't define TypeScript interfaces inline in the page file — put them in `types/index.ts`
- Don't use TanStack Table for simple list pages — use native HTML `<table>`
- Don't use Tailwind color classes for badges — use Radix `<Badge>` with color props
- Don't use random ports — frontend is 5174, backend is 8099
- Don't add your own nav chrome — pages render inside `<Outlet />` in AppLayout
- Don't use `useRef` or `useMemo` after an early return — all hooks before any returns
- Don't forget to run `cd frontend && npx tsc` to check for type errors before committing
