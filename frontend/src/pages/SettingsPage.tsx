import { useState, useEffect, useCallback } from "react";
import { Heading, Text, Badge, Button } from "@radix-ui/themes";
import { Star, MagnifyingGlass, CaretDown, Check } from "@phosphor-icons/react";
import { fetchApi, postApi, mutateApi } from "../api/client";
import { categoryColor } from "../lib/theme";
import { getRadixHex } from "../lib/theme";
import type { BrandItem, BrandBrowseResponse, BrandCategory, BrandCategoriesResponse } from "../types";

// ============================================================
// Category Picker Dropdown
// ============================================================

function CategoryPicker({
  current,
  categories,
  onSelect,
}: {
  current: string | null;
  categories: BrandCategory[];
  onSelect: (category: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-[var(--radius-2)] text-[13px] border border-[var(--gray-6)] hover:bg-[var(--gray-3)] transition-colors"
        style={{ color: current ? "var(--gray-12)" : "var(--gray-9)" }}
      >
        {current ? (
          <>
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ background: getRadixHex(categoryColor(current), 9) }}
            />
            {current}
          </>
        ) : (
          "Set category"
        )}
        <CaretDown size={12} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 top-full mt-1 z-20 rounded-[var(--radius-2)] border border-[var(--gray-6)] py-1 min-w-[180px]"
            style={{ background: "var(--gray-1)" }}
          >
            {categories.map((cat) => (
              <button
                key={cat.id}
                onClick={() => {
                  onSelect(cat.id);
                  setOpen(false);
                }}
                className="flex items-center gap-2 w-full px-3 py-1.5 text-[13px] text-left hover:bg-[var(--gray-3)] transition-colors"
                style={{ color: "var(--gray-12)" }}
              >
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: getRadixHex(cat.color, 9) }}
                />
                {cat.id}
                {current === cat.id && (
                  <Check size={14} className="ml-auto" style={{ color: "var(--accent-9)" }} />
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================
// Settings Page
// ============================================================

type ShowFilter = "all" | "favorites" | "not_favorites" | "uncategorized";

export default function SettingsPage() {
  const [brands, setBrands] = useState<BrandItem[]>([]);
  const [categories, setCategories] = useState<BrandCategory[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [showFilter, setShowFilter] = useState<ShowFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const perPage = 50;

  // Debounced search
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, showFilter, categoryFilter]);

  // Load categories once
  useEffect(() => {
    fetchApi<BrandCategoriesResponse>("/brands/categories").then((res) =>
      setCategories(res.categories)
    );
  }, []);

  // Load brands
  const loadBrands = useCallback(() => {
    setLoading(true);
    const params: Record<string, string> = {
      page: String(page),
      per_page: String(perPage),
    };
    if (debouncedSearch) params.search = debouncedSearch;
    if (categoryFilter) params.category = categoryFilter;
    if (showFilter === "favorites") params.favorites_only = "true";
    if (showFilter === "not_favorites") {
      // We'll filter client-side for this one since API doesn't have this param
    }

    fetchApi<BrandBrowseResponse>("/brands", params)
      .then((res) => {
        let filtered = res.brands;
        if (showFilter === "not_favorites") {
          filtered = filtered.filter((b) => !b.is_favorite);
        }
        if (showFilter === "uncategorized") {
          filtered = filtered.filter((b) => !b.category);
        }
        setBrands(filtered);
        setTotal(showFilter === "not_favorites" || showFilter === "uncategorized" ? filtered.length : res.total);
      })
      .finally(() => setLoading(false));
  }, [page, perPage, debouncedSearch, categoryFilter, showFilter]);

  useEffect(() => {
    loadBrands();
  }, [loadBrands]);

  // Toggle favorite
  const toggleFavorite = async (brand: string, currentlyFavorite: boolean) => {
    if (currentlyFavorite) {
      await mutateApi("/brands/favorites", "DELETE", { brands: [brand] });
    } else {
      await postApi("/brands/favorites", { brands: [brand] });
    }
    // Update local state immediately
    setBrands((prev) =>
      prev.map((b) =>
        b.brand === brand ? { ...b, is_favorite: !currentlyFavorite } : b
      )
    );
  };

  // Set category
  const setCategory = async (brand: string, category: string) => {
    await mutateApi("/brands/category", "PUT", { brand, category });
    setBrands((prev) =>
      prev.map((b) => (b.brand === brand ? { ...b, category } : b))
    );
  };

  const pages = Math.ceil(total / perPage) || 1;

  return (
    <div className="p-6 max-w-[960px]">
      <Heading size="6" className="mb-1">
        Settings
      </Heading>
      <Text size="2" style={{ color: "var(--gray-9)" }} className="mb-6 block">
        Manage your brand preferences and app configuration.
      </Text>

      {/* Brand Favorites Section */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <div className="flex items-center justify-between mb-1">
          <Heading size="4">Brand Favorites</Heading>
        </div>
        <Text size="2" style={{ color: "var(--gray-9)" }} className="mb-4 block">
          Your favorite brands appear in filter dropdowns on the Map, Properties, and Groups pages.
          Star the brands you care about. Assign categories to uncategorized brands so they appear
          in category-based filters.
        </Text>

        {/* Filters Row */}
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <MagnifyingGlass
              size={16}
              className="absolute left-2.5 top-1/2 -translate-y-1/2"
              style={{ color: "var(--gray-9)" }}
            />
            <input
              type="text"
              placeholder="Search brands..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-2 rounded-[var(--radius-2)] border border-[var(--gray-6)] text-[14px] outline-none"
              style={{
                background: "var(--gray-1)",
                color: "var(--gray-12)",
              }}
            />
          </div>

          {/* Show filter */}
          <select
            value={showFilter}
            onChange={(e) => setShowFilter(e.target.value as ShowFilter)}
            className="px-3 py-2 rounded-[var(--radius-2)] border border-[var(--gray-6)] text-[13px]"
            style={{ background: "var(--gray-1)", color: "var(--gray-12)" }}
          >
            <option value="all">All brands</option>
            <option value="favorites">Favorites only</option>
            <option value="not_favorites">Not favorited</option>
            <option value="uncategorized">Uncategorized</option>
          </select>

          {/* Category filter */}
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="px-3 py-2 rounded-[var(--radius-2)] border border-[var(--gray-6)] text-[13px]"
            style={{ background: "var(--gray-1)", color: "var(--gray-12)" }}
          >
            <option value="">All categories</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.id}
              </option>
            ))}
          </select>
        </div>

        {/* Brand Table */}
        <div className="rounded-[var(--radius-2)] border border-[var(--gray-6)] overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--gray-2)]">
                <th
                  className="text-left px-3 py-2 text-[12px] font-medium w-10"
                  style={{ color: "var(--gray-9)" }}
                >
                  Fav
                </th>
                <th
                  className="text-left px-3 py-2 text-[12px] font-medium"
                  style={{ color: "var(--gray-9)" }}
                >
                  Brand
                </th>
                <th
                  className="text-left px-3 py-2 text-[12px] font-medium w-[180px]"
                  style={{ color: "var(--gray-9)" }}
                >
                  Category
                </th>
                <th
                  className="text-right px-3 py-2 text-[12px] font-medium w-[80px]"
                  style={{ color: "var(--gray-9)" }}
                >
                  Locations
                </th>
                <th
                  className="text-center px-3 py-2 text-[12px] font-medium w-[70px]"
                  style={{ color: "var(--gray-9)" }}
                >
                  Source
                </th>
              </tr>
            </thead>
            <tbody>
              {loading && brands.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center">
                    <Text size="2" style={{ color: "var(--gray-9)" }}>
                      Loading brands...
                    </Text>
                  </td>
                </tr>
              ) : brands.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center">
                    <Text size="2" style={{ color: "var(--gray-9)" }}>
                      No brands match your filters.
                    </Text>
                  </td>
                </tr>
              ) : (
                brands.map((b) => (
                  <tr
                    key={b.brand}
                    className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] transition-colors"
                  >
                    {/* Star */}
                    <td className="px-3 py-2">
                      <button
                        onClick={() => toggleFavorite(b.brand, b.is_favorite)}
                        className="flex items-center justify-center w-7 h-7 rounded-[var(--radius-2)] hover:bg-[var(--gray-3)] transition-colors"
                      >
                        <Star
                          size={18}
                          weight={b.is_favorite ? "fill" : "regular"}
                          style={{
                            color: b.is_favorite ? "var(--amber-9)" : "var(--gray-7)",
                          }}
                        />
                      </button>
                    </td>
                    {/* Brand name */}
                    <td className="px-3 py-2">
                      <Text size="2" weight="medium">
                        {b.brand}
                      </Text>
                    </td>
                    {/* Category */}
                    <td className="px-3 py-2">
                      <CategoryPicker
                        current={b.category}
                        categories={categories}
                        onSelect={(cat) => setCategory(b.brand, cat)}
                      />
                    </td>
                    {/* POI count */}
                    <td className="px-3 py-2 text-right">
                      <Text size="2" style={{ color: "var(--gray-11)" }}>
                        {b.poi_count.toLocaleString()}
                      </Text>
                    </td>
                    {/* Curated badge */}
                    <td className="px-3 py-2 text-center">
                      {b.is_curated ? (
                        <Badge color="jade" variant="soft" size="1">
                          CSV
                        </Badge>
                      ) : (
                        <Badge color="gray" variant="soft" size="1">
                          OSM
                        </Badge>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between mt-3">
            <Text size="2" style={{ color: "var(--gray-9)" }}>
              Page {page} of {pages} ({total.toLocaleString()} brands)
            </Text>
            <div className="flex gap-2">
              <Button
                variant="soft"
                size="1"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <Button
                variant="soft"
                size="1"
                disabled={page >= pages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
