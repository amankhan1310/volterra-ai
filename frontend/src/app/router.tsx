import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, useLocation, type RouteObject } from "react-router";
import { Skeleton } from "../components/ui/States";
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
 * Every page, each lazy-loaded so the charting library is fetched with the first page that draws
 * a chart, not with the shell. Typed as a complete record: a page without a component does not
 * compile.
 */
export const PAGE_COMPONENTS: Record<PageKey, ComponentType> = {
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
  anom: lazy(() =>
    import("../features/anomalies/AnomaliesPage").then((m) => ({
      default: m.AnomaliesPage,
    })),
  ),
  advisor: lazy(() =>
    import("../features/advisor/AdvisorPage").then((m) => ({
      default: m.AdvisorPage,
    })),
  ),
  about: lazy(() =>
    import("../features/about/AboutPage").then((m) => ({
      default: m.AboutPage,
    })),
  ),
};

function PageRoute({ pageKey }: { pageKey: PageKey }) {
  const Page = PAGE_COMPONENTS[pageKey];
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
