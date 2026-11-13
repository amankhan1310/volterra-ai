import { useCallback, useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router";
import { Header } from "../components/layout/Header";
import { Sidebar } from "../components/layout/Sidebar";
import { MOBILE_QUERY, useMediaQuery } from "../lib/useMediaQuery";
import styles from "./AppLayout.module.css";
import { findPageByPath } from "./pages";

/** Sidebar + header + scrolling main area (legacy index.html shell). */
export function AppLayout() {
  const location = useLocation();
  const page = findPageByPath(location.pathname);
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
  }, []);

  useEffect(() => {
    document.title = page
      ? `${page.label} · VOLTERRA AI`
      : "Page not found · VOLTERRA AI";
  }, [page]);

  // Like the legacy router, every page starts at the top.
  useEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [drawerOpen]);

  const drawerVisible = isMobile && drawerOpen;

  return (
    <div className={styles.shell}>
      <a
        href="#main"
        className={styles.skip}
        onClick={(e) => {
          e.preventDefault();
          mainRef.current?.focus();
        }}
      >
        Skip to content
      </a>
      <Sidebar
        collapsed={collapsed && !isMobile}
        drawerOpen={drawerVisible}
        inert={isMobile && !drawerOpen}
        onNavigate={closeDrawer}
      />
      {drawerVisible ? (
        <div
          className={styles.backdrop}
          onClick={closeDrawer}
          aria-hidden="true"
        />
      ) : null}
      <div className={styles.col}>
        <Header
          page={page}
          drawerOpen={drawerVisible}
          onToggleDrawer={() => {
            setDrawerOpen((open) => !open);
          }}
          collapsed={collapsed}
          onToggleCollapse={() => {
            setCollapsed((c) => !c);
          }}
          onNavigate={closeDrawer}
        />
        <main id="main" ref={mainRef} tabIndex={-1} className={styles.main}>
          <div className={styles.page}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
