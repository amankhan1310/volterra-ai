import { Navigate, useLocation, type RouteObject } from "react-router";
import { PlaceholderPage } from "../features/placeholder/PlaceholderPage";
import { AppLayout } from "./AppLayout";
import { NotFoundPage } from "./NotFoundPage";
import { PAGES, pathForLegacyHash } from "./pages";
import { RouteError } from "./RouteError";

/** `/` goes to Overview; legacy bookmarks such as `/#sim` go to the matching page. */
function RootRedirect() {
  const { hash } = useLocation();
  return <Navigate to={pathForLegacyHash(hash) ?? "/overview"} replace />;
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
        element: <PlaceholderPage pageKey={page.key} />,
      })),
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
