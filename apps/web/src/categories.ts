/**
 * Shopping categories, style tags and tones from GET /api/categories (docs/contracts/accessories.md). Pickers, size
 * inputs and style chips are built from the server's lists. If the call fails (an older server, or offline), the
 * garment-only list the server has always accepted is used, so manual crop never offers a category the server would
 * refuse, and the style and tone vocabularies are empty, so no chip is offered that the server might not know.
 */
import { useEffect, useState } from "react";
import type { CategoriesResponse, CategoryInfo } from "@contracts";
import { api } from "./api";

export type StyleTag = CategoriesResponse["styleTags"][number];
export type Tone = CategoriesResponse["tones"][number];

const GARMENT_KEYS: CategoryInfo["attributeKeys"] = ["color", "pattern", "cut", "details"];
export const LEGACY_CATEGORIES: CategoryInfo[] = [
  { id: "jacket", label: "Jacket", family: "apparel", sizeRule: "clothing", attributeKeys: GARMENT_KEYS },
  { id: "top", label: "Top", family: "apparel", sizeRule: "clothing", attributeKeys: GARMENT_KEYS },
  { id: "pants", label: "Pants", family: "apparel", sizeRule: "clothing", attributeKeys: GARMENT_KEYS },
  { id: "bag", label: "Bag", family: "bag", sizeRule: "clothing", attributeKeys: GARMENT_KEYS },
  { id: "other", label: "Other", family: "other", sizeRule: "none", attributeKeys: ["color", "details"] },
];

const FALLBACK = { list: LEGACY_CATEGORIES, styleTags: [] as StyleTag[], tones: [] as Tone[] };

export interface Categories {
  list: CategoryInfo[];
  styleTags: StyleTag[];
  tones: Tone[];
  /** "server" when the list came from /api/categories; "fallback" when the call failed. */
  origin: "loading" | "server" | "fallback";
}

export function useCategories(): Categories {
  const [c, setC] = useState<Categories>({ ...FALLBACK, origin: "loading" });
  useEffect(() => {
    let live = true;
    api
      .categories()
      .then(
        (r) =>
          live &&
          setC(
            r.categories?.length
              ? { list: r.categories, styleTags: r.styleTags ?? [], tones: r.tones ?? [], origin: "server" }
              : { ...FALLBACK, origin: "fallback" },
          ),
      )
      .catch(() => live && setC({ ...FALLBACK, origin: "fallback" }));
    return () => {
      live = false;
    };
  }, []);
  return c;
}

export const categoryOf = (list: CategoryInfo[], id: string | null | undefined): CategoryInfo | null =>
  list.find((c) => c.id === id) ?? null;

/** Watches and jewelry: appearance-only wording, "Similar look" tier, tone chips. */
export const isAccessory = (c: CategoryInfo | null) => c?.family === "watch" || c?.family === "jewelry";

/** Manual crop: "other" is only a relabel target (the server's crop route doesn't accept it). */
export const croppable = (list: CategoryInfo[]) => list.filter((c) => c.id !== "other");

/** Picker groups: clothing and bags first, then watches and jewelry, then other. */
export function grouped(list: CategoryInfo[]): { label: string; items: CategoryInfo[] }[] {
  const g = [
    { label: "Clothing and bags", items: list.filter((c) => c.family === "apparel" || c.family === "bag") },
    { label: "Watches and jewelry", items: list.filter((c) => c.family === "watch" || c.family === "jewelry") },
    { label: "Other", items: list.filter((c) => c.family === "other") },
  ];
  return g.filter((x) => x.items.length);
}

// Attribute keys, worded per family. Accessories describe tone and form only, never metal or authenticity.
const ATTR_LABEL: Record<string, Record<string, string>> = {
  default: { color: "Color", pattern: "Pattern", cut: "Cut", details: "Details" },
  accessory: { color: "Tone and color", pattern: "Pattern", cut: "Form", details: "Visible details" },
};
export const attrLabel = (c: CategoryInfo | null, key: string) =>
  (isAccessory(c) ? ATTR_LABEL.accessory : ATTR_LABEL.default)[key] ?? key.charAt(0).toUpperCase() + key.slice(1);

/** US ring sizes as the server accepts them (app/categories.py norm_ring_size): 3–15, with .25, .5 or .75. */
export function ringSize(raw: string): string | null {
  const t = raw.trim().replace(/\s*½$/, ".5").replace(/\s*¼$/, ".25").replace(/\s*¾$/, ".75");
  const m = /^(?:us\s*)?(?:size\s*)?(\d{1,2})(?:\.(5|25|75))?$/i.exec(t);
  if (!m || Number(m[1]) < 3 || Number(m[1]) > 15) return null;
  return m[2] ? `${Number(m[1])}.${m[2]}` : String(Number(m[1]));
}
