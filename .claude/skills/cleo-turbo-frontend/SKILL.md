---
name: cleo-turbo-frontend
description: >
  Skill for working on the Cleo Turbo frontend — a commercial real estate data platform built with
  React 19, TypeScript, Vite, Radix UI Themes (jade/slate), Tailwind CSS, and Phosphor Icons.
  Use this skill whenever the user wants to build, edit, fix, or style any frontend page or component
  in the Cleo Turbo app. This includes adding new pages, editing existing pages, creating or modifying
  components, fixing layout or styling issues, adding new routes, working with the API client,
  updating TypeScript types, or making any visual change to the app. Also use this skill when the user
  mentions Cleo Turbo and frontend work in the same breath, or refers to pages like "the properties page",
  "the map", "the dashboard", "deals page", "contacts", "pipeline", etc. Even if the user just says
  something casual like "make the table look better" or "add a column" — if it's about Cleo Turbo's UI,
  use this skill.
---

# Cleo Turbo Frontend Development

You are working on Cleo Turbo, a commercial real estate data platform for Ontario. The user (Brandon) is a vibe coder — he relies on you to know the codebase conventions and make good decisions. Don't ask him to choose between technical approaches; pick the one that fits the existing patterns and explain what you did after.

## Before You Write Any Code

1. Read `CLAUDE.md` in the project root — it has the canonical rules, project structure, and step-by-step checklists for adding pages and API routes
2. Look at an existing page similar to what you're building (the pages are in `frontend/src/pages/`)
3. Check `frontend/src/types/index.ts` for existing TypeScript interfaces you can reuse or extend
4. Check `frontend/src/lib/utils.ts` and `frontend/src/lib/theme.ts` for existing helpers — don't reinvent these

## Tech Stack Quick Reference

- **React 19** with TypeScript 5.9, built with **Vite 8**
- **Radix UI Themes** (`@radix-ui/themes`) — the semantic component library. Use `<Heading>`, `<Text>`, `<Badge>`, `<Button>`, `<Tabs>`, `<DataList>`, `<Callout>`, `<TextField>`, `<Separator>` from here
- **Tailwind CSS 3.4** — for layout, spacing, and utility classes only. Don't use Tailwind for colors; use CSS variables instead
- **Phosphor Icons** (`@phosphor-icons/react`) — the icon library. Import like `import { Buildings, User, MagnifyingGlass } from "@phosphor-icons/react"`
- **Radix color system via CSS variables** — e.g., `var(--jade-9)`, `var(--gray-11)`, `var(--accent-11)`
- **react-router-dom v7** — for routing, `useParams`, `useNavigate`, `useLocation`
- **Mapbox GL** via `react-map-gl` — for any map features
- **Recharts** — for charts and data visualization
- **TanStack Table + TanStack Virtual** — for complex data tables with sorting/filtering/virtualization
- **clsx + tailwind-merge** — for conditional class composition

## Design System Rules

The app follows a WorkOS Dashboard aesthetic — clean, professional, data-dense.

### Theme
The Radix `<Theme>` wrapper uses: `accentColor="jade"` `grayColor="slate"` `radius="medium"`. The font is "Untitled Sans". Don't change these.

### Colors
Always use CSS variables, never raw hex or Tailwind color classes:
- Primary/accent: `var(--jade-9)`, `var(--accent-9)`, `var(--accent-11)`
- Text: `var(--gray-12)` (primary), `var(--gray-11)` (secondary), `var(--gray-9)` (muted)
- Borders: `var(--gray-6)`
- Subtle backgrounds: `var(--gray-2)`, `var(--gray-3)`
- Links: `color: var(--accent-11)` with `text-decoration: none`

Exception: Mapbox can't read CSS variables. Use `getRadixHex()` from `lib/theme.ts` to get hex values for map layers.

### Cards
```
className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5"
```
The `--card-radius` variable is `12px`. Use this pattern consistently for all card containers.

### Tables
For simple list pages, use plain HTML `<table>` elements (not TanStack Table):
- Table header: `className="bg-[var(--gray-2)]"` with cells using `text-[12px] font-medium` and `style={{ color: "var(--gray-9)" }}`
- Row hover: make rows clickable with `onClick={() => navigate(...)}` and `cursor-pointer hover:bg-[var(--gray-2)]`
- Use TanStack Table only for complex tables that need sorting, filtering, column resizing, or virtualization

### Typography
Use Radix components, not raw HTML:
- Page titles: `<Heading size="6">` 
- Section titles: `<Heading size="4">`
- Body text: `<Text>`
- Status labels: `<Badge>`
- Don't use `<h1>`, `<h2>`, `<p>` directly for visible content

### Spacing and Layout
- Page padding: `p-6` on the outer wrapper
- Card grids: use CSS grid (`grid grid-cols-2 gap-4` or `grid grid-cols-3 gap-4`)
- Detail pages: typically a 2-column or 3-column layout with cards
- Back links at the top of detail pages: `← Resource Name` linking to the list page

## Page Patterns

### List Pages
```tsx
// Pattern: fetch paginated data, render a table, navigate on row click
const [data, setData] = useState<BrowseResponse<YourType> | null>(null);
const [page, setPage] = useState(1);

useEffect(() => {
  fetchApi<BrowseResponse<YourType>>("/your-resource", { page, per_page: 25 })
    .then(setData);
}, [page]);
```

### Detail Pages
```tsx
// Pattern: load by ID from URL params, show cards with related data
const { id } = useParams();
const [item, setItem] = useState<YourDetail | null>(null);

useEffect(() => {
  fetchApi<YourDetail>(`/your-resource/${id}`).then(setItem);
}, [id]);
```

### Lazy-loaded Pages
Heavy pages (map, pipeline, data-quality) use `React.lazy()` + `<Suspense>`:
```tsx
const MapPage = lazy(() => import("./pages/MapPage"));
// In routes: <Route path="/map" element={<Suspense fallback={...}><MapPage /></Suspense>} />
```

## API Client

Three helpers in `src/api/client.ts`:
- `fetchApi<T>(path, params?)` — GET with query params
- `postApi<T>(path, body)` — POST with JSON body  
- `mutateApi<T>(path, method, body?)` — PUT/PATCH/DELETE

Path is relative to `/api` — e.g., `fetchApi("/properties")` hits `/api/properties`. Auth token is attached automatically. 401 responses redirect to `/login`.

## State Management

- **Auth**: `useAuth()` hook from `hooks/useAuth.ts` — provides `user`, `token`, `login()`, `logout()`
- **CRM drawer**: `useCrm()` hook from `components/crm/CrmContext.tsx` — opens the entity side drawer
- **Everything else**: local `useState` in components. No Redux, no Zustand. Keep it simple.

## File Organization

- Pages go in `src/pages/` — one file per page, default export
- Shared components go in `src/components/` organized by domain (`auth/`, `crm/`, `layout/`, `pipeline/`, `ui/`)
- Types go in `src/types/index.ts` — all interfaces in one file
- Utility functions go in `src/lib/utils.ts`
- Theme/color helpers go in `src/lib/theme.ts`

## Adding a New Page Checklist

1. Create `frontend/src/pages/YourPage.tsx`
2. Add TypeScript interfaces to `frontend/src/types/index.ts`
3. Add route in `App.tsx` inside the `<Route element={<AppLayout />}>` block
4. Import at top of `App.tsx` (use `lazy()` only for heavy pages)
5. If it needs a sidebar link, add it in `components/layout/Sidebar.tsx`
6. If it's full-bleed (like the map), add to `FULL_BLEED_ROUTES` in `AppLayout.tsx`

## Formatting Helpers

Always use these from `lib/utils.ts` — don't format inline:
- `formatCurrency(amount)` — Canadian dollars
- `formatDate(dateStr)` — consistent date formatting
- `formatPhone(phone)` — phone number formatting
- `titleCase(str)` — title casing

## Color Mappings

`lib/theme.ts` has semantic color functions — use these instead of hardcoding:
- `propertyTypeColor(type)` — maps property types to Radix colors
- `categoryColor(category)` — maps tenant categories to colors
- `dealStageLabel(stage)` — formats deal stages with colors

## Before Committing

Run `cd frontend && npx tsc` to check for TypeScript errors. Fix any errors before committing. The database, clean-data, and raw-data directories are gitignored — only code is tracked.

## Ports

Never change these:
- Backend: **8099**
- Frontend dev server: **5174** (strictPort in vite.config.ts)
- Vite proxies `/api` to `http://127.0.0.1:8099`
