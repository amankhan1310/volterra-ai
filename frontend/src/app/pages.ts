/**
 * The six prototype pages. Labels, groups, titles and subtitles are copied verbatim from
 * legacy/core.js (`names`) and legacy/ui.js (`head(...)` calls and the nav groups).
 */
export type PageKey =
  | "overview"
  | "digital"
  | "sim"
  | "anom"
  | "advisor"
  | "about";

export type NavGroup = "Monitor" | "Plan" | "Project";

export interface PageMeta {
  /** Legacy page key, also the legacy URL hash (`#sim`). */
  key: PageKey;
  path: string;
  /** Navigation label (legacy `names`). */
  label: string;
  title: string;
  subtitle: string;
  /** Phase 4 milestone that rebuilds the page. */
  milestone: number;
  /** True once that milestone has shipped; until then the route shows a labelled placeholder. */
  built: boolean;
}

/** Order of the legacy quick-navigation select (`Object.entries(names)`). */
export const PAGES: readonly PageMeta[] = [
  {
    key: "overview",
    path: "/overview",
    label: "Overview",
    title: "Battery Intelligence",
    subtitle:
      "Understand degradation. Anticipate risk. Make smarter battery decisions.",
    milestone: 2,
    built: true,
  },
  {
    key: "digital",
    path: "/digital-twin",
    label: "Digital Twin",
    title: "Battery Digital Twin",
    subtitle:
      "A software representation driven by the selected cycle of the dataset. It is not connected to a vehicle.",
    milestone: 3,
    built: true,
  },
  {
    key: "sim",
    path: "/simulator",
    label: "What-If Simulator",
    title: "What-If Simulator",
    subtitle:
      "Compare operating scenarios against a 25 °C, 1C, 80% DoD baseline.",
    milestone: 4,
    built: true,
  },
  {
    key: "anom",
    path: "/anomalies",
    label: "Anomaly Detection",
    title: "Anomaly Detection",
    subtitle:
      "Robust z-score (median/MAD, threshold 3.5). Events are patterns to investigate, not confirmed faults.",
    milestone: 5,
    built: true,
  },
  {
    key: "advisor",
    path: "/advisor",
    label: "Charging Advisor",
    title: "Charging Advisor",
    subtitle:
      "How each change would move cycles to end-of-life, under this simulator’s assumed coefficients.",
    milestone: 5,
    built: true,
  },
  {
    key: "about",
    path: "/about",
    label: "About",
    title: "About",
    subtitle: "Project information, method and limits.",
    milestone: 6,
    built: false,
  },
];

/** Sidebar groups (legacy ui.js `$("nav").innerHTML`). */
export const NAV_GROUPS: readonly {
  group: NavGroup;
  keys: readonly PageKey[];
}[] = [
  { group: "Monitor", keys: ["overview", "digital", "anom"] },
  { group: "Plan", keys: ["sim", "advisor"] },
  { group: "Project", keys: ["about"] },
];

const BY_KEY = new Map(PAGES.map((p) => [p.key, p]));

export function getPage(key: PageKey): PageMeta {
  const page = BY_KEY.get(key);
  if (!page) throw new Error(`Unknown page: ${key}`);
  return page;
}

export function findPageByPath(pathname: string): PageMeta | undefined {
  const normalised =
    pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return PAGES.find((p) => p.path === normalised);
}

/** Maps a legacy URL hash (`#anom`) to the new route, so old bookmarks keep working. */
export function pathForLegacyHash(hash: string): string | undefined {
  const key = hash.replace(/^#/, "");
  return PAGES.find((p) => p.key === key)?.path;
}
