import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, RouterProvider, createMemoryRouter } from "react-router";
import { AppProviders } from "../app/providers";
import { routes } from "../app/router";
import { ScenarioDraftProvider } from "../state/ScenarioDraftContext";

export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
    },
  });
}

/** Mounts the real app (providers, router, layout) at `path`. */
export function renderApp(path = "/overview") {
  const client = testQueryClient();
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const user = userEvent.setup();
  const utils = render(
    <AppProviders client={client}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...utils, client, router, user };
}

/** Mounts a component inside the app providers, a router at `path` and the scenario draft. */
export function renderWithProviders(ui: ReactElement, path = "/") {
  const client = testQueryClient();
  const user = userEvent.setup();
  const utils = render(
    <AppProviders client={client}>
      <MemoryRouter initialEntries={[path]}>
        <ScenarioDraftProvider>{ui}</ScenarioDraftProvider>
      </MemoryRouter>
    </AppProviders>,
  );
  return { ...utils, client, user };
}
