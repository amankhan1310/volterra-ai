import { useCallback, useState } from "react";

/**
 * Colour theme (decision D2, approved in M6): dark on a first visit, a header toggle switches to
 * light, and the choice is remembered in this browser. index.html applies a saved choice before
 * the first paint (no flash of the wrong theme); this module keeps it in sync afterwards.
 */
export type Theme = "dark" | "light";

/** Storage key; index.html reads the same key in its inline script. */
export const THEME_STORAGE_KEY = "volterra-theme";

export function currentTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "light"
    ? "light"
    : "dark";
}

/** Applies a theme to the document and remembers it (storage may be unavailable: then it lasts until reload). */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Private mode or blocked storage: the theme still applies for this page view.
  }
  // Browser chrome (mobile address bar) follows the page background token.
  const background = getComputedStyle(root).getPropertyValue("--bg").trim();
  if (background)
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", background);
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  const toggle = useCallback(() => {
    const next: Theme = currentTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  }, []);
  return { theme, toggle };
}
