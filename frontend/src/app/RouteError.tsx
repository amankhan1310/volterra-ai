import { useRouteError } from "react-router";
import { ErrorState } from "../components/ui/States";

/** Last-resort boundary for errors thrown while rendering a route. */
export function RouteError() {
  const error = useRouteError();
  const message =
    error instanceof Error ? error.message : "The page failed to render.";
  return (
    <div style={{ maxWidth: 720, margin: "48px auto", padding: "0 16px" }}>
      <ErrorState
        title="Something went wrong"
        message={message}
        hint="Reload the page. If it keeps happening, the browser console has details."
        onRetry={() => {
          window.location.reload();
        }}
      />
    </div>
  );
}
