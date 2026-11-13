import { useId, type ReactNode } from "react";
import type { PageKey } from "../../app/pages";

/** Line icons copied from legacy/ui.js (`ICO`, burger, collapse and bell buttons). */
function Icon({
  size = 18,
  strokeWidth = 1.7,
  children,
}: {
  size?: number;
  strokeWidth?: number;
  children: ReactNode;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

const PAGE_ICON_PATHS: Record<PageKey, ReactNode> = {
  overview: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </>
  ),
  digital: (
    <>
      <path d="M12 2l9 5v10l-9 5-9-5V7z" />
      <path d="M12 22V12M3 7l9 5 9-5" />
    </>
  ),
  sim: (
    <>
      <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12" />
      <circle cx="16" cy="6" r="2" />
      <circle cx="10" cy="12" r="2" />
      <circle cx="18" cy="18" r="2" />
    </>
  ),
  anom: (
    <>
      <path d="M12 3l10 18H2z" />
      <path d="M12 10v5M12 18h.01" />
    </>
  ),
  advisor: <path d="M13 2L4 14h7l-1 8 9-12h-7z" />,
  about: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </>
  ),
};

export function PageIcon({ page }: { page: PageKey }) {
  return <Icon>{PAGE_ICON_PATHS[page]}</Icon>;
}

export function BurgerIcon() {
  return (
    <Icon size={20} strokeWidth={1.8}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Icon>
  );
}

export function CollapseIcon() {
  return (
    <Icon strokeWidth={1.8}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </Icon>
  );
}

export function BellIcon() {
  return (
    <Icon strokeWidth={1.8}>
      <path d="M6 9a6 6 0 0112 0c0 6 2 7 2 7H4s2-1 2-7M10 20a2 2 0 004 0" />
    </Icon>
  );
}

/** Brand mark (legacy ui.js `$("brand")`); the gradient id is unique per instance. */
export function BrandMark() {
  const gradient = `brand-${useId().replace(/:/g, "")}`;
  return (
    <svg
      width="32"
      height="32"
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--cy)" />
          <stop offset="1" stopColor="var(--ib)" />
        </linearGradient>
      </defs>
      <path
        d="M16 2l12 7v14l-12 7-12-7V9z"
        fill="none"
        stroke={`url(#${gradient})`}
        strokeWidth="1.8"
      />
      <rect
        x="10"
        y="16"
        width="3"
        height="6"
        rx="1"
        fill={`url(#${gradient})`}
      />
      <rect
        x="14.5"
        y="12"
        width="3"
        height="10"
        rx="1"
        fill={`url(#${gradient})`}
      />
      <rect
        x="19"
        y="8"
        width="3"
        height="14"
        rx="1"
        fill={`url(#${gradient})`}
      />
    </svg>
  );
}
