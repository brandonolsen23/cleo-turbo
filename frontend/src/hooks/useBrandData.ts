/**
 * useBrandData — API-backed brand data hook.
 *
 * Replaces the hardcoded brandCategories.ts. Fetches the user's favorite
 * brands from the API and provides the same interface (BRAND_TO_CATEGORY,
 * CATEGORY_TO_BRANDS, expandBrandFilter) but driven by live data.
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { fetchApi, postApi, mutateApi } from "../api/client";
import type {
  BrandFavorite,
  BrandFavoritesResponse,
  BrandCategory,
  BrandCategoriesResponse,
} from "../types";

interface BrandData {
  /** All favorite brands */
  favorites: BrandFavorite[];
  /** Brand → category lookup (favorites only) */
  brandToCategory: Record<string, string>;
  /** Category → sorted brand list (favorites only) */
  categoryToBrands: Record<string, string[]>;
  /** All favorite brand names, sorted */
  allBrands: string[];
  /** Available categories with colors */
  categories: BrandCategory[];
  /** Loading state */
  loading: boolean;
  /** Expand selected categories + brands into full brand set */
  expandBrandFilter: (
    selectedCategories: Set<string>,
    selectedBrands: Set<string>
  ) => Set<string>;
  /** Refresh data from API */
  refresh: () => void;
  /** Add brands to favorites */
  addFavorites: (brands: string[]) => Promise<void>;
  /** Remove brands from favorites */
  removeFavorites: (brands: string[]) => Promise<void>;
}

export function useBrandData(): BrandData {
  const [favorites, setFavorites] = useState<BrandFavorite[]>([]);
  const [categories, setCategories] = useState<BrandCategory[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetchApi<BrandFavoritesResponse>("/brands/favorites"),
      fetchApi<BrandCategoriesResponse>("/brands/categories"),
    ])
      .then(([favRes, catRes]) => {
        setFavorites(favRes.favorites);
        setCategories(catRes.categories);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const brandToCategory = useMemo(() => {
    const map: Record<string, string> = {};
    for (const f of favorites) {
      if (f.category) map[f.brand] = f.category;
    }
    return map;
  }, [favorites]);

  const categoryToBrands = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const cat of categories) {
      map[cat.id] = [];
    }
    for (const f of favorites) {
      if (f.category && map[f.category]) {
        map[f.category].push(f.brand);
      }
    }
    for (const key of Object.keys(map)) {
      map[key].sort();
    }
    return map;
  }, [favorites, categories]);

  const allBrands = useMemo(
    () => favorites.map((f) => f.brand).sort(),
    [favorites]
  );

  const expandBrandFilter = useCallback(
    (selectedCategories: Set<string>, selectedBrands: Set<string>) => {
      const result = new Set(selectedBrands);
      for (const cat of selectedCategories) {
        const brands = categoryToBrands[cat];
        if (brands) {
          for (const b of brands) result.add(b);
        }
      }
      return result;
    },
    [categoryToBrands]
  );

  const addFavorites = useCallback(
    async (brands: string[]) => {
      await postApi("/brands/favorites", { brands });
      fetchData();
    },
    [fetchData]
  );

  const removeFavorites = useCallback(
    async (brands: string[]) => {
      await mutateApi("/brands/favorites", "DELETE", { brands });
      fetchData();
    },
    [fetchData]
  );

  return {
    favorites,
    brandToCategory,
    categoryToBrands,
    allBrands,
    categories,
    loading,
    expandBrandFilter,
    refresh: fetchData,
    addFavorites,
    removeFavorites,
  };
}
