// ============================================================
// Brand → Category mapping
// Source: Master Retail Sheet - All Brands.csv
// ============================================================

export const RETAIL_CATEGORIES = [
  "Grocery",
  "Big-Box Retail",
  "Discount Retail",
  "Specialty Retail",
  "QSR",
  "Full-Service",
  "Take-out",
  "Fuel",
  "Financial Services",
  "Automotive",
] as const;

export type RetailCategory = (typeof RETAIL_CATEGORIES)[number];

/** Every brand and the category it belongs to. */
export const BRAND_TO_CATEGORY: Record<string, RetailCategory> = {
  // Grocery
  "Loblaws": "Grocery",
  "NoFrills": "Grocery",
  "Real Canadian Superstore": "Grocery",
  "Shoppers Drug Mart": "Grocery",
  "Zehrs": "Grocery",
  "Fortinos": "Grocery",
  "Valu-Mart": "Grocery",
  "Independant": "Grocery",
  "Wholesale Club": "Grocery",
  "Sobeys": "Grocery",
  "FreshCo": "Grocery",
  "Foodland": "Grocery",
  "Longos": "Grocery",
  "Farm Boy": "Grocery",
  "Safeway": "Grocery",
  "Metro": "Grocery",
  "Food Basics": "Grocery",

  // Big-Box Retail
  "Walmart": "Big-Box Retail",
  "Canadian Tire": "Big-Box Retail",
  "Rona": "Big-Box Retail",
  "Home Hardware": "Big-Box Retail",
  "Home Depot": "Big-Box Retail",
  "Costco": "Big-Box Retail",

  // Discount Retail
  "Giant Tiger": "Discount Retail",
  "Dollarama": "Discount Retail",
  "Dollar Tree": "Discount Retail",
  "Goodwill": "Discount Retail",
  "Winners": "Discount Retail",

  // Specialty Retail
  "Best Buy": "Specialty Retail",
  "Staples": "Specialty Retail",
  "Jysk": "Specialty Retail",
  "HomeSense": "Specialty Retail",
  "Indigo / Chapters": "Specialty Retail",
  "La-Z-Boy": "Specialty Retail",
  "Pet Smart": "Specialty Retail",
  "Pet Valu": "Specialty Retail",
  "Sport Chek": "Specialty Retail",
  "The Brick": "Specialty Retail",
  "Leon's": "Specialty Retail",
  "Tepperman's": "Specialty Retail",
  "Beer Store": "Specialty Retail",
  "LCBO": "Specialty Retail",
  "Toys R Us": "Specialty Retail",
  "Mastermind Toys": "Specialty Retail",
  "Rens Pets": "Specialty Retail",

  // QSR
  "McDonalds": "QSR",
  "A&W": "QSR",
  "Wendy's": "QSR",
  "Burger King": "QSR",
  "Harvey's": "QSR",
  "KFC": "QSR",
  "Taco Bell": "QSR",
  "Arby's": "QSR",
  "Tim Hortons": "QSR",
  "Mary Brown's Chicken": "QSR",
  "Popeyes Louisiana Kitchen": "QSR",
  "Starbucks": "QSR",
  "Dairy Queen": "QSR",
  "Swiss Chalet": "QSR",

  // Full-Service
  "Kelseys Original Roadhouse": "Full-Service",
  "Montana's BBQ & Bar": "Full-Service",
  "East Side Mario's": "Full-Service",
  "Earls": "Full-Service",
  "Applebees": "Full-Service",
  "Boston Pizza": "Full-Service",
  "Chipotle Mexican Grill": "Full-Service",
  "Chick-fil-A": "Full-Service",
  "Cora": "Full-Service",
  "Denny's": "Full-Service",
  "Five Guys": "Full-Service",
  "Milestones Grill & Bar": "Full-Service",
  "St. Louis Bar & Grill": "Full-Service",
  "Wimpy's Diner": "Full-Service",
  "The Works": "Full-Service",
  "Red Lobster": "Full-Service",
  "Stacked Pancake House": "Full-Service",
  "Barburrito": "Full-Service",
  "Sunset Grill": "Full-Service",
  "Wild Wing": "Full-Service",
  "Halubut House": "Full-Service",

  // Take-out
  "Booster Juice": "Take-out",
  "Baskin Robbins": "Take-out",
  "Dominos Pizza": "Take-out",
  "Pizza Nova": "Take-out",
  "Pizza Hut": "Take-out",
  "Pizza Pizza": "Take-out",
  "Pita Pit": "Take-out",
  "Freshii": "Take-out",
  "Firehouse Subs": "Take-out",
  "Godfather's Pizza": "Take-out",
  "Little Caesars": "Take-out",
  "Marble Slab Creamery": "Take-out",
  "Mr. Sub": "Take-out",
  "Mucho Burrito": "Take-out",
  "Papa John's": "Take-out",
  "Subway": "Take-out",
  "The Great Canadian Bagel": "Take-out",
  "Guac": "Take-out",
  "Osmow's": "Take-out",
  "Wok Box": "Take-out",

  // Fuel
  "Petro Can": "Fuel",
  "Esso": "Fuel",
  "Shell": "Fuel",
  "Ultrimar": "Fuel",
  "Can-Co": "Fuel",
  "MacEwen": "Fuel",
  "Husky": "Fuel",
  "Pioneer": "Fuel",
  "Mobil": "Fuel",

  // Financial Services
  "CIBC": "Financial Services",
  "TD": "Financial Services",
  "Scotia Bank": "Financial Services",
  "RBC": "Financial Services",
  "BMO": "Financial Services",
  "Libro Credit Union": "Financial Services",

  // Automotive
  "Toyota": "Automotive",
  "Lexus": "Automotive",
  "Honda": "Automotive",
  "Acura": "Automotive",
  "Nissan": "Automotive",
  "Infiniti": "Automotive",
  "Kia": "Automotive",
  "Hyundai": "Automotive",
  "Volvo": "Automotive",
  "Chrysler": "Automotive",
  "Ford": "Automotive",
  "GMC": "Automotive",
  "Mercedes-Benz": "Automotive",
  "Porsche": "Automotive",
  "Land-Rover": "Automotive",
  "Volkswagen": "Automotive",
  "Audi": "Automotive",
  "BMW": "Automotive",
  "Jaguar": "Automotive",
  "Mazda": "Automotive",
  "Mitsubishi": "Automotive",
};

/** Inverted index: category → sorted brand list */
export const CATEGORY_TO_BRANDS: Record<RetailCategory, string[]> = {} as any;
for (const cat of RETAIL_CATEGORIES) {
  CATEGORY_TO_BRANDS[cat] = [];
}
for (const [brand, cat] of Object.entries(BRAND_TO_CATEGORY)) {
  CATEGORY_TO_BRANDS[cat].push(brand);
}
for (const cat of RETAIL_CATEGORIES) {
  CATEGORY_TO_BRANDS[cat].sort();
}

/** All brand names, sorted alphabetically */
export const ALL_BRANDS = Object.keys(BRAND_TO_CATEGORY).sort();

/**
 * Given selected categories and selected brands, returns the full set
 * of brand names to filter against.
 */
export function expandBrandFilter(
  selectedCategories: Set<string>,
  selectedBrands: Set<string>,
): Set<string> {
  const result = new Set(selectedBrands);
  for (const cat of selectedCategories) {
    const brands = CATEGORY_TO_BRANDS[cat as RetailCategory];
    if (brands) {
      for (const b of brands) result.add(b);
    }
  }
  return result;
}
