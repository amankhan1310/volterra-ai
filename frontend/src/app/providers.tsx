import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ToastProvider } from "../components/ui/Toast";
import { ScenarioDraftProvider } from "../state/ScenarioDraftContext";

export function AppProviders({
  client,
  children,
}: {
  client: QueryClient;
  children: ReactNode;
}) {
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ScenarioDraftProvider>{children}</ScenarioDraftProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
