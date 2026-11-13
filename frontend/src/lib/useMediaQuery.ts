import { useSyncExternalStore } from "react";

/** Legacy breakpoint where the sidebar becomes an off-canvas drawer (style.css:829). */
export const MOBILE_QUERY = "(max-width: 860px)";

/** Live result of a CSS media query. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => {
        mql.removeEventListener("change", onChange);
      };
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
