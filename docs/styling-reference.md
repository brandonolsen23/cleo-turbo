# Cleo V4 — Design System & Styling Reference

Extracted from V3's production frontend (March 2026). This is a self-contained
reference for rebuilding the UI in V4 without any dependency on V3's codebase or
data layer. Copy the font files and config patterns — nothing here touches the
V3 database.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Dependencies](#2-dependencies)
3. [Font Files](#3-font-files)
4. [Tailwind Configuration](#4-tailwind-configuration)
5. [Radix Theme Setup](#5-radix-theme-setup)
6. [CSS Custom Properties](#6-css-custom-properties)
7. [Global CSS](#7-global-css)
8. [Typography](#8-typography)
9. [Color System](#9-color-system)
10. [Spacing & Layout](#10-spacing--layout)
11. [Cards & Containers](#11-cards--containers)
12. [Borders & Radius](#12-borders--radius)
13. [Elevation & Shadows](#13-elevation--shadows)
14. [Sidebar Navigation](#14-sidebar-navigation)
15. [Data Tables](#15-data-tables)
16. [Page Headers](#16-page-headers)
17. [Empty States](#17-empty-states)
18. [Badges & Category Colors](#18-badges--category-colors)
19. [Charts](#19-charts)
20. [Drawers (Slide Panels)](#20-drawers-slide-panels)
21. [Map Styling](#21-map-styling)
22. [Animations & Transitions](#22-animations--transitions)
23. [Utility Functions](#23-utility-functions)
24. [Radix Hex Lookup (for Mapbox)](#24-radix-hex-lookup-for-mapbox)
25. [Anti-Patterns (Do NOT)](#25-anti-patterns-do-not)
26. [Checklist for New Components](#26-checklist-for-new-components)

---

## 1. Architecture Overview

The design system is called "WorkOS Dashboard" — it replicates the look of the
WorkOS admin dashboard. Three files define the entire system:

```
tailwind.config.js   — Font family, font weight remapping
src/lib/theme.ts     — Radix Theme props, chart colors, color maps
src/index.css        — @font-face, CSS custom properties, Radix overrides
```

**Stack:** Tailwind CSS (utility classes) + Radix Themes (component library +
color tokens) + custom CSS properties (layout/elevation). No CSS-in-JS. No
per-component CSS files. All styling is either Tailwind classes on elements or
inline `style={{}}` objects using CSS variables.

**Class merging:** `cn()` utility (clsx + tailwind-merge) for conditional classes.

---

## 2. Dependencies

```json
{
  "dependencies": {
    "@radix-ui/themes": "^3.3.0",
    "@radix-ui/react-icons": "^1.3.2",
    "@phosphor-icons/react": "^2.1.10",
    "@tanstack/react-table": "^8.21.2",
    "@tanstack/react-virtual": "^3.11.3",
    "clsx": "^2.1.1",
    "tailwind-merge": "^3.5.0",
    "recharts": "^3.7.0",
    "mapbox-gl": "^3.18.1",
    "react-map-gl": "^8.1.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^7.1.1"
  },
  "devDependencies": {
    "tailwindcss": "^3.4.17",
    "postcss": "^8.4.49",
    "autoprefixer": "^10.4.20",
    "typescript": "^5.7.3",
    "vite": "^6.0.7",
    "@vitejs/plugin-react": "^4.3.4"
  }
}
```

**Icon libraries:**
- `@phosphor-icons/react` — Primary (7000+ icons, used everywhere)
- `@radix-ui/react-icons` — Secondary (17 icons for sidebar nav)

**No other UI libraries** — no shadcn, Material-UI, Chakra, etc.

---

## 3. Font Files

**Font:** Untitled Sans by Klim Type Foundry (same as WorkOS dashboard).

Six files needed (copy from V3's `frontend/src/assets/fonts/`):

```
UntitledSans-Regular.woff2   UntitledSans-Regular.woff    (weight 400)
UntitledSans-Medium.woff2    UntitledSans-Medium.woff     (weight 500)
UntitledSans-Bold.woff2      UntitledSans-Bold.woff       (weight 700)
```

Bold (700) is registered but **never used in the UI**. WorkOS's "bold" is
actually Medium (500). We register it anyway so the font doesn't break if
someone accidentally uses 700.

---

## 4. Tailwind Configuration

```js
// tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    fontFamily: {
      sans: [
        '"Untitled Sans"',
        "-apple-system",
        "BlinkMacSystemFont",
        '"Segoe UI"',
        "Helvetica",
        "Arial",
        "sans-serif",
      ],
    },
    fontWeight: {
      light: "300",
      normal: "400",
      medium: "500",
      semibold: "500",   // Remapped — same as medium
      bold: "500",       // Remapped — same as medium
    },
  },
  plugins: [],
};
```

**Key:** `semibold` and `bold` are remapped to 500 so any Tailwind class that
would normally produce 600/700 renders as Medium instead. This matches WorkOS.

**PostCSS:** Standard two-plugin setup — `tailwindcss` + `autoprefixer`.

```js
// postcss.config.js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

---

## 5. Radix Theme Setup

In your app entry point (`main.tsx`):

```tsx
import "@radix-ui/themes/styles.css";
import "./index.css";

import { Theme } from "@radix-ui/themes";

// Theme constants (keep in lib/theme.ts)
export const THEME = {
  accentColor: "jade" as const,
  grayColor: "slate" as const,
  radius: "medium" as const,
  scaling: "100%" as const,
} as const;

// In render:
<Theme
  accentColor={THEME.accentColor}
  grayColor={THEME.grayColor}
  radius={THEME.radius}
  scaling={THEME.scaling}
  appearance="light"
>
  <App />
</Theme>
```

**Import order matters:** Radix styles first, then your index.css (so your
overrides cascade on top).

**No dark mode** — `appearance="light"` is hardcoded. All color decisions assume
light mode.

---

## 6. CSS Custom Properties

### `:root` tokens

```css
:root {
  /* Elevation shadows */
  --elevation-1: 0px 0px 0px 1px rgba(0, 0, 0, 0.1);
  --elevation-2: 0px 4px 8px -2px rgba(0, 0, 0, 0.05),
                 0px 2px 8px -2px rgba(0, 0, 0, 0.09);
  --elevation-3: 0px 8px 16px -4px rgba(0, 0, 0, 0.03),
                 0px 8px 16px -4px rgba(0, 0, 0, 0.09);
  --elevation-4: 0px 16px 24px -6px rgba(0, 0, 0, 0.03),
                 0px 16px 24px -6px rgba(0, 0, 0, 0.09);

  /* Layout */
  --sidebar-width: 220px;
  --header-height: 56px;
  --card-radius: 12px;
  --card-padding: 24px;
}
```

### Radix-provided tokens (runtime, not in `:root`)

These come from the `<Theme>` component at runtime:

```
--gray-1 through --gray-12        (solid colors)
--gray-a1 through --gray-a12      (alpha/transparent variants)
--accent-1 through --accent-12    (theme accent = jade)
--{color}-1 through --{color}-12  (every named Radix color)
--radius-1 through --radius-6     (border radii)
--font-size-1 through --font-size-9
```

### Radix overrides (on `.radix-themes` selector)

```css
.radix-themes {
  --default-font-family: "Untitled Sans", -apple-system, BlinkMacSystemFont,
    "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  --heading-font-family: "Untitled Sans", -apple-system, BlinkMacSystemFont,
    "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  --code-font-family: "SF Mono", "Menlo", "Consolas", monospace;

  /* WorkOS custom slate-12 (extracted from their dashboard) */
  --slate-12: #2b333b;
  --slate-a12: rgba(0, 10, 19, 0.832);

  min-height: 100vh;
}

.rt-Heading {
  font-weight: 500;
  letter-spacing: 0em;
}
```

---

## 7. Global CSS

Complete `index.css` structure for V4:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ---- @font-face ---- */

@font-face {
  font-family: "Untitled Sans";
  src: url("./assets/fonts/UntitledSans-Regular.woff2") format("woff2"),
       url("./assets/fonts/UntitledSans-Regular.woff") format("woff");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}

@font-face {
  font-family: "Untitled Sans";
  src: url("./assets/fonts/UntitledSans-Medium.woff2") format("woff2"),
       url("./assets/fonts/UntitledSans-Medium.woff") format("woff");
  font-weight: 500;
  font-style: normal;
  font-display: swap;
}

@font-face {
  font-family: "Untitled Sans";
  src: url("./assets/fonts/UntitledSans-Bold.woff2") format("woff2"),
       url("./assets/fonts/UntitledSans-Bold.woff") format("woff");
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}

/* ---- Design tokens ---- */

:root {
  --elevation-1: 0px 0px 0px 1px rgba(0, 0, 0, 0.1);
  --elevation-2: 0px 4px 8px -2px rgba(0, 0, 0, 0.05),
    0px 2px 8px -2px rgba(0, 0, 0, 0.09);
  --elevation-3: 0px 8px 16px -4px rgba(0, 0, 0, 0.03),
    0px 8px 16px -4px rgba(0, 0, 0, 0.09);
  --elevation-4: 0px 16px 24px -6px rgba(0, 0, 0, 0.03),
    0px 16px 24px -6px rgba(0, 0, 0, 0.09);

  --sidebar-width: 220px;
  --header-height: 56px;
  --card-radius: 12px;
  --card-padding: 24px;
}

/* ---- Global body ---- */

body {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ---- Radix Themes overrides ---- */

.radix-themes {
  --default-font-family: "Untitled Sans", -apple-system, BlinkMacSystemFont,
    "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  --heading-font-family: "Untitled Sans", -apple-system, BlinkMacSystemFont,
    "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  --code-font-family: "SF Mono", "Menlo", "Consolas", monospace;
  --slate-12: #2b333b;
  --slate-a12: rgba(0, 10, 19, 0.832);
  min-height: 100vh;
}

.rt-Heading {
  font-weight: 500;
  letter-spacing: 0em;
}

/* ---- App Layout Grid ---- */

.app-layout {
  display: grid;
  grid-template:
    "navbar header" var(--header-height)
    "navbar main"   calc(100dvh - var(--header-height))
    / var(--sidebar-width) 1fr;
  height: 100dvh;
}

.app-sidebar {
  grid-area: navbar;
  --nav-text-inactive: var(--gray-11);
  --nav-text-active:   var(--gray-12);
  --nav-icon-inactive: var(--gray-a9);
  --nav-icon-active:   var(--gray-a9);
  --nav-active-bg:     var(--gray-a4);
  --nav-hover-bg:      var(--gray-a3);
}

.app-header {
  grid-area: header;
  position: sticky;
  top: 0;
  z-index: 1;
}

.app-main {
  grid-area: main;
  overflow-y: auto;
  position: relative;
}

.app-main:has(.page-full-bleed) {
  overflow: hidden;
}

.app-main-content {
  max-width: 72rem;
  margin-left: auto;
  margin-right: auto;
  padding: 24px 24px 64px;
}

.app-main-content:has(> .page-full-bleed) {
  max-width: none;
  margin: 0;
  padding: 0;
  height: 100%;
  overflow: hidden;
}

.page-full-bleed {
  height: 100%;
}
```

---

## 8. Typography

### Weight rules

| Tailwind class  | CSS weight | Font file | Usage                           |
|-----------------|------------|-----------|---------------------------------|
| `font-normal`   | 400        | Regular   | Body text, inactive nav         |
| `font-medium`   | 500        | Medium    | Headings, emphasis, active nav  |
| `font-semibold` | 500        | Medium    | Remapped (same as medium)       |
| `font-bold`     | 500        | Medium    | Remapped (same as medium)       |

### Text sizes used in V3

| Context              | Class/Style                                            |
|----------------------|--------------------------------------------------------|
| Page heading         | `text-[24px] font-medium leading-[32px] tracking-[0]` |
| Body text            | `text-[14px] leading-[20px]`                           |
| Empty state title    | `text-[16px] font-medium leading-[24px]`               |
| Table header         | `text-[12px] font-medium leading-[16px]`               |
| Table cell           | `text-[14px] leading-[20px]`                           |
| Sidebar nav item     | `font-size: var(--font-size-2)` (14px)                 |
| Sidebar group header | `font-size: 12px; font-weight: 500`                   |

### Radix text components

```tsx
<Heading size="5" weight="medium">Page Title</Heading>
<Text size="2" color="gray">Secondary text</Text>
<Text size="2" weight="medium">Emphasized text</Text>
```

**Never use** `weight="bold"` on Radix `<Heading>` or `<Text>` — it bypasses
the Tailwind remap and produces actual 700. Use `weight="medium"` instead.

---

## 9. Color System

### Gray scale (Radix "slate")

| Token       | Usage                                                     |
|-------------|-----------------------------------------------------------|
| `--gray-1`  | Page background, drawer background                        |
| `--gray-2`  | Sidebar bg, table header bg, popup close button bg        |
| `--gray-3`  | Hover backgrounds (nav, popup close)                      |
| `--gray-4`  | Subtle borders, inner dividers, sidebar edge, drawer edge |
| `--gray-6`  | Card borders, input borders, table outer border, popup border |
| `--gray-7`  | Stronger input borders                                    |
| `--gray-8`  | Neutral chart fill, sort caret inactive, empty state icon |
| `--gray-9`  | Muted text (descriptions, placeholders, table headers, popup close) |
| `--gray-11` | Secondary text, inactive nav text/icons                   |
| `--gray-12` | Primary text, headings, active nav text, sort caret active |

### Alpha variants (`--gray-aN`)

| Token        | Usage                    |
|--------------|--------------------------|
| `--gray-a2`  | Table row hover bg       |
| `--gray-a3`  | Nav hover background     |
| `--gray-a4`  | Nav active background    |
| `--gray-a9`  | Nav icon color           |

### Accent color (jade)

Use `--accent-N` for anything theme-colored. Use `--jade-N` only in chart
palettes or when you specifically need jade regardless of theme.

### Semantic colors

| Purpose          | Text token     | Fill token    |
|------------------|----------------|---------------|
| Positive/success | `--green-11`   | `--green-9`   |
| Negative/error   | `--red-11`     | `--red-9`     |
| Warning          | `--amber-11`   | `--amber-3`   |
| Neutral          | `--gray-8`     | —             |

### WorkOS custom overrides

V3 overrides two Radix tokens to match WorkOS's exact slate-12:

```css
--slate-12: #2b333b;
--slate-a12: rgba(0, 10, 19, 0.832);
```

These are the **only** hardcoded hex/rgba values that are intentional (besides
elevation shadows and Mapbox paint expressions).

---

## 10. Spacing & Layout

### Spacing scale

| Scale   | Tailwind | Pixels | Usage                                |
|---------|----------|--------|--------------------------------------|
| Section | `gap-6`  | 24px   | Between major page sections          |
| Grid    | `gap-4`  | 16px   | Between cards in a grid row          |
| Inner   | `gap-2`  | 8px    | Between elements inside a card       |
| Tight   | `gap-1`  | 4px    | Between small elements (badge icons) |
| Nav gap | `gap-px` | 1px    | Between sidebar nav items            |

### Layout tokens

| Token               | Value  | Usage                               |
|----------------------|--------|-------------------------------------|
| `--sidebar-width`    | 220px  | Left navigation panel               |
| `--header-height`    | 56px   | Top header bar                      |
| `--card-padding`     | 24px   | Defined but `p-5`=20px is standard  |

### Page content wrapper

```css
.app-main-content {
  max-width: 72rem;      /* 1152px */
  margin-left: auto;
  margin-right: auto;
  padding: 24px 24px 64px;
}
```

### Full-bleed pages (e.g. Map)

Add class `page-full-bleed` to the page root. CSS `:has()` selectors reset
`app-main-content` to fill the entire viewport.

---

## 11. Cards & Containers

**Standard card:**

```tsx
<div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
  {/* content */}
</div>
```

- Radius: `var(--card-radius)` = 12px
- Border: `var(--gray-6)` (1px solid)
- Padding: `p-5` (20px) — **always p-5** for cards
- Inner dividers: `border-[var(--gray-4)]`

**Do not** use `p-4`, `p-6`, or `p-8` for card padding. Always `p-5`.

---

## 12. Borders & Radius

| Token                    | Value    | Usage                         |
|--------------------------|----------|-------------------------------|
| `var(--card-radius)`     | 12px     | Cards, major containers       |
| `var(--radius-2)`        | ~4-6px   | Buttons, pills, inputs, nav items |
| `var(--radius-3)`        | ~6-8px   | Tooltips, dropdowns, popups   |
| `var(--radius-4)`        | ~8-10px  | Table wrapper outer border    |

`--radius-2/3/4` are provided by Radix Themes at runtime. They adapt to the
`THEME.radius` setting ("medium").

### Border colors

| Context        | Token                     |
|----------------|---------------------------|
| Card border    | `border-[var(--gray-6)]`  |
| Inner divider  | `border-[var(--gray-4)]`  |
| Sidebar edge   | `border-[var(--gray-4)]`  |
| Table header   | `border-[var(--gray-6)]`  |
| Table row      | `border-[var(--gray-4)]`  |
| Table wrapper  | `border-[var(--gray-6)]`  |
| Drawer edge    | `border-[var(--gray-4)]`  |

---

## 13. Elevation & Shadows

Four levels, used instead of Tailwind shadow classes:

```css
--elevation-1   /* Subtle outline — input focus ring */
--elevation-2   /* Card hover, map popups */
--elevation-3   /* Drawer panels, dropdowns */
--elevation-4   /* Modal dialogs */
```

Usage: `box-shadow: var(--elevation-2)` in inline styles, or
`shadow-[var(--elevation-2)]` in Tailwind.

---

## 14. Sidebar Navigation

### CSS tokens (scoped to `.app-sidebar`)

```css
.app-sidebar {
  --nav-text-inactive: var(--gray-11);
  --nav-text-active:   var(--gray-12);
  --nav-icon-inactive: var(--gray-a9);
  --nav-icon-active:   var(--gray-a9);
  --nav-active-bg:     var(--gray-a4);
  --nav-hover-bg:      var(--gray-a3);
}
```

### Nav item styling (inline style object)

```tsx
{
  display: "flex",
  alignItems: "center",
  gap: 8,
  height: 36,
  padding: "0 9px",
  borderRadius: "var(--radius-2)",
  fontSize: "var(--font-size-2)",    // 14px
  fontWeight: active ? 500 : 400,
  lineHeight: 1,
  color: active ? "var(--nav-text-active)" : "var(--nav-text-inactive)",
  background: active ? "var(--nav-active-bg)" : "transparent",
  whiteSpace: "nowrap",
  userSelect: "none",
  transition: "background 80ms ease-out, color 80ms ease-out",
}
```

### Nav icon sizing

- Radix icons (sidebar): `width={18} height={18}`
- Phosphor icons (content): `size={16}` or `size={18}` with `weight="bold"`

### Sidebar structure

```
nav.app-sidebar (bg: --gray-2, border-r: --gray-4)
  +-- Logo area (height: 56px, px-5)
  +-- Scrollable nav area (flex-1)
      +-- Nav groups (p-3 pb-6, gap-0.5)
      |   +-- Group heading (12px, weight 500, --gray-9, + <Separator>)
      |   +-- Nav items (gap-px between)
      +-- Footer (p-3 pt-0)
          +-- <Separator>
          +-- Settings item
```

---

## 15. Data Tables

### HTML structure

```tsx
<div className="overflow-hidden rounded-[var(--radius-4)] border border-[var(--gray-6)]">
  <table className="w-full border-collapse text-left">
    <thead>
      <tr className="border-b border-[var(--gray-6)] bg-[var(--gray-2)]">
        <th className="px-4 py-2.5 text-left">
          <span className="text-[12px] font-medium leading-[16px] text-[var(--gray-11)]">
            Column Header
          </span>
          {/* Sort carets: CaretUp + CaretDown, size={9}, weight="fill" */}
          {/* Active: text-[var(--gray-12)], Inactive: text-[var(--gray-8)] */}
        </th>
      </tr>
    </thead>
    <tbody>
      <tr className="border-b border-[var(--gray-4)] last:border-b-0 cursor-pointer hover:bg-[var(--gray-2)]">
        <td className="px-4 py-2.5 text-[14px] leading-[20px] text-[var(--gray-12)]">
          Cell content
        </td>
      </tr>
    </tbody>
  </table>
</div>
```

### Empty state in table

```tsx
<td colSpan={columns.length} className="py-10 text-center">
  <Text size="2" color="gray">{emptyMessage}</Text>
</td>
```

---

## 16. Page Headers

```tsx
<div className="flex items-start justify-between" style={{ minHeight: 32 }}>
  <div>
    <h2 className="text-[24px] font-medium leading-[32px] tracking-[0] text-[var(--gray-12)]">
      {title}
    </h2>
    <p className="mt-1 text-[14px] leading-[20px] text-[var(--gray-9)]">
      {description}
    </p>
  </div>
  <div className="flex items-center gap-2">{actions}</div>
</div>
```

Optional `<TabNav.Root>` below with `className="mt-4"`.

---

## 17. Empty States

```tsx
<div className="flex flex-col items-center justify-center py-16">
  <div className="mb-4 text-[var(--gray-8)]">{icon}</div>
  <span className="text-[16px] font-medium leading-[24px] text-[var(--gray-12)]">
    {title}
  </span>
  <span className="mt-1 max-w-sm text-center text-[14px] leading-[20px] text-[var(--gray-9)]">
    {description}
  </span>
  <Button variant="soft" size="2" className="mt-4" onClick={...}>
    {action.label}
  </Button>
</div>
```

---

## 18. Badges & Category Colors

### Brand categories (10)

```ts
const CATEGORY_COLORS = {
  grocery:             "lime",
  qsr:                 "orange",
  "big-box retail":    "blue",
  "specialty retail":  "plum",
  "discount retail":   "amber",
  "full-service":      "violet",
  "take-out":          "pink",
  automotive:          "tomato",
  "financial services":"cyan",
  fuel:                "indigo",
};
```

### Property types (12)

```ts
const PROPERTY_TYPE_COLORS = {
  retail:           "jade",
  industrial:       "orange",
  multifamily:      "blue",
  office:           "cyan",
  farm:             "lime",
  "res-land":       "sky",
  "comm-ind-land":  "amber",
  "hotel-motel":    "violet",
  "restaurant-bar": "pink",
  "other-bldg":     "gray",
  "other-land":     "brown",
  all:              "iris",
  untyped:          "gray",
};
```

### Badge pattern

```tsx
<Badge variant="soft" color={categoryColor(category)}>
  {categoryLabel(category)}
</Badge>
```

Radix `<Badge variant="soft">` automatically uses alpha backgrounds at the
correct shade for the given color.

### Theme customization (localStorage-backed)

V3 supports user-overridable colors stored in localStorage:
- `cleo_category_colors` — category color overrides
- `cleo_ptype_colors` — property type color overrides
- `cleo_selection_color` — map selection highlight color (default: amber)

Overrides are loaded on init, applied via getter functions
(`categoryColor()`, `propertyTypeColor()`), and persisted with
`setCategoryColor()`, `setPropertyTypeColor()`. A listener system
(`onThemeChange()`) triggers re-renders when colors change.

---

## 19. Charts

**Library:** Recharts v3

### Color palette

```ts
export const CHART_COLORS = {
  primary: [
    "var(--jade-11)",   // darkest
    "var(--jade-9)",
    "var(--jade-7)",
    "var(--jade-4)",    // lightest
  ],
  accent: "var(--accent-9)",
  positive: "var(--green-11)",
  negative: "var(--red-11)",
  neutral: "var(--gray-8)",
};
```

### Custom tooltip pattern

```tsx
<div style={{
  border: "1px solid var(--gray-6)",
  borderRadius: "var(--radius-2)",
  background: "var(--gray-1)",
  boxShadow: "var(--elevation-2)",
  padding: "8px 12px",
}}>
  {/* tooltip content */}
</div>
```

To change the chart accent: update `CHART_COLORS.primary` array to use
`--{newColor}-11/9/7/4` tokens.

---

## 20. Drawers (Slide Panels)

### CSS pattern

```css
.drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  /* transparent — just catches clicks to close */
}

.drawer {
  position: fixed;
  top: var(--header-height);
  right: 0;
  bottom: 0;
  width: 420px;              /* CRM: 420px, AI: 440px */
  z-index: 50;
  display: flex;
  flex-direction: column;
  background: var(--gray-1);
  border-left: 1px solid var(--gray-4);
  box-shadow: var(--elevation-3);
  transform: translateX(100%);
  transition: transform 200ms ease-out;
  overflow: hidden;
}

.drawer--open {
  transform: translateX(0);
}
```

---

## 21. Map Styling

### Mapbox GL styles

- Main map: `mapbox://styles/mapbox/satellite-streets-v12`
- Detail mini-map: `mapbox://styles/mapbox/light-v11`

### Popup overrides (in index.css)

```css
.mapboxgl-popup-content {
  padding: 12px 14px !important;
  border-radius: var(--radius-3) !important;
  border: 1px solid var(--gray-6);
  box-shadow: var(--elevation-2) !important;
  font-family: "Untitled Sans", -apple-system, BlinkMacSystemFont, sans-serif;
}

.mapboxgl-popup-close-button {
  font-size: 14px;
  width: 22px;
  height: 22px;
  color: var(--gray-9);
  background: var(--gray-2);
  border: 1px solid var(--gray-6);
  border-radius: var(--radius-2);
  right: -8px;
  top: -8px;
}

.mapboxgl-popup-close-button:hover {
  color: var(--gray-12);
  background: var(--gray-3);
}

.mapboxgl-popup-anchor-bottom .mapboxgl-popup-tip {
  border-top-color: var(--gray-6);
}
```

### Mapbox paint expressions

Mapbox GL cannot use CSS variables. Use a static hex lookup table
(`getRadixHex(color, step)`) to resolve Radix colors to hex at runtime.

---

## 22. Animations & Transitions

### Drawer slide-in
```css
transition: transform 200ms ease-out;
/* closed: translateX(100%)  ->  open: translateX(0) */
```

### Nav item hover
```css
transition: background 80ms ease-out, color 80ms ease-out;
```

### Scan pulse (monitor grid)
```css
@keyframes scan-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
/* animation: scan-pulse 1.5s ease-in-out infinite; */
```

**No animation libraries** — no Framer Motion, react-spring, etc.

---

## 23. Utility Functions

### `cn()` — class merging

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

### Formatters

```ts
formatCompact(n)    // 1200 -> "1.2k", 1500000 -> "1.5M"
formatCurrency(n)   // 250000 -> "$250,000" (CAD, no decimals)
formatPercent(n)     // 5.3 -> "+5.3%", -2.1 -> "-2.1%"
titleCase(s)         // "MAIN STREET" -> "Main Street"
formatStreet(addr)   // "123 MAIN STREET NORTH" -> "123 Main St N"
formatDate(iso)      // "2026-02-20" -> "Feb 20, 2026"
```

---

## 24. Radix Hex Lookup (for Mapbox)

Mapbox GL requires hex strings in paint expressions. V3 has a static sRGB hex
table for all 23 Radix colors at all 12 steps (276 entries). Key values:

```
jade-9:   #29a383
jade-11:  #208368
green-9:  #30a46c
red-9:    #e5484d
amber-9:  #ffc53d
blue-9:   #0090ff
orange-9: #f76b15
cyan-9:   #00a2c7
violet-9: #6e56cf
pink-9:   #d6409f
lime-9:   #bdee63
plum-9:   #ab4aba
tomato-9: #e54d2e
indigo-9: #3e63dd
sky-9:    #7ce2fe
brown-9:  #ad7f58
iris-9:   #5b5bd6
gray-9:   #8d8d8d
slate-9:  #8b8d98
```

Full table (all 12 steps for all colors) lives in `theme.ts`. Copy to V4 if
using Mapbox GL.

---

## 25. Anti-Patterns (Do NOT)

1. **No `fontWeight: 700`** in any inline style or Tailwind class
2. **No `weight="bold"`** on Radix `<Heading>` or `<Text>` — use `weight="medium"`
3. **No hardcoded hex colors** for UI elements — use `--gray-N` / `--accent-N` tokens
4. **No `rgba()` for grays** — use `--gray-aN` alpha tokens instead
5. **No `p-4`, `p-6`, or `p-8`** for card padding — always `p-5`
6. **No Tailwind shadow classes** (`shadow-sm`, `shadow-md`) — use `--elevation-N`
7. **No new `@font-face` entries** without updating this doc
8. **No custom color variables** — check Radix's palette first
9. **No CSS-in-JS** (styled-components, emotion, etc.)
10. **No per-component CSS files** — everything in Tailwind classes or index.css

---

## 26. Checklist for New Components

Before writing any component, verify:

- [ ] Text color: `text-[var(--gray-12)]` (primary) or `text-[var(--gray-9)]` (secondary)
- [ ] Font weight: `font-medium` for emphasis, `font-normal` for body
- [ ] Borders: `border-[var(--gray-6)]` for cards, `border-[var(--gray-4)]` for dividers
- [ ] Radius: `rounded-[var(--card-radius)]` for cards
- [ ] Padding: `p-5` inside cards
- [ ] Gaps: `gap-6` sections, `gap-4` grids, `gap-2` inner
- [ ] Accent colors: `var(--accent-9)` not hardcoded color names
- [ ] Hover states: `hover:bg-[var(--gray-a3)]`
- [ ] No `fontWeight: 700`, no hardcoded hex, no `rgba()` grays

---

## Appendix: Radix Components Used in V3

For reference, all Radix components imported across V3:

**Layout/Typography:** `Text`, `Heading`, `Separator`, `Code`
**Forms:** `TextField`, `TextArea`, `Select`, `Checkbox`, `Switch`
**Feedback:** `Spinner`, `Callout`, `Tooltip`
**Actions:** `Button`, `IconButton`, `DropdownMenu`
**Data:** `Badge`, `DataList`, `Avatar`, `Card`
**Navigation:** `Tabs`, `TabNav`, `Dialog`

---

## Appendix: All Radix Color Names

Available for `accentColor`, badge `color`, or `--{name}-N` tokens:

```
tomato  red     ruby    crimson  pink    plum
purple  violet  iris    indigo   blue    cyan
teal    jade    green   grass    lime    mint
sky     yellow  amber   orange   brown   gray
```
