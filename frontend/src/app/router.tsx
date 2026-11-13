import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, useLocation, type RouteObject } from "react-router";
import { Skeleton } from "../components/ui/States";
import { PlaceholderPage } from "../features/placeholder/PlaceholderPage";
import { AppLayout } from "./AppLayout";
import { NotFoundPage } from "./NotFoundPage";
import { PAGES, pathForLegacyHash, type PageKey } from "./pages";
import { RouteError } from "./RouteError";

/** `/` goes to Overview; legacy bookmarks such as `/#sim` go to the matching page. */
function RootRedirect() {
  const { hash } = useLocation();
  return <Navigate to={pathForLegacyHash(hash) ?? "/overview"} replace />;
}

/**
 * Rebuilt pages, each lazy-loaded so the charting library is fetched with the first page that
 * draws a chart, not with the shell. Pages not listed here show their labelled placeholder.
 */
export const BUILT: Partial<Record<PageKey, ComponentType>> = {
  overview: lazy(() =>
    import("../features/overview/OverviewPage").then((m) => ({
      default: m.OverviewPage,
    })),
  ),
  digital: lazy(() =>
    import("../features/digital-twin/DigitalTwinPage").then((m) => ({
      default: m.DigitalTwinPage,
    })),
  ),
  sim: lazy(() =>
    import("../features/simulator/SimulatorPage").then((m) => ({
      default: m.SimulatorPage,
    })),
  ),
};

function PageRoute({ pageKey }: { pageKey: PageKey }) {
  const Page = BUILT[pageKey];
  if (!Page) return <PlaceholderPage pageKey={pageKey} />;
  return (
    <Suspense fallback={<Skeleton label="Loading page" height={340} />}>
      <Page />
    </Suspense>
  );
}

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppLayout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <RootRedirect /> },
      ...PAGES.map((page) => ({
        path: page.path.slice(1),
        element: <PageRoute pageKey={page.key} />,
      })),
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
