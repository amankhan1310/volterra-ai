import { ApiError } from "./client";

export interface ErrorDescription {
  title: string;
  message: string;
  /** What the user can do about it. */
  hint?: string;
  code?: string;
}

export const START_API_HINT =
  "Start the backend: cd backend && uv run uvicorn --factory app.main:create_app --reload";
export const START_DB_HINT =
  "Start PostgreSQL and check DATABASE_URL in backend/.env, then retry.";

/** Turns any thrown value into text for an error state. */
export function describeError(error: unknown): ErrorDescription {
  if (!(error instanceof ApiError)) {
    return {
      title: "Unexpected error",
      message: error instanceof Error ? error.message : String(error),
    };
  }
  if (error.code === "api_unreachable") {
    return {
      title: "API unreachable",
      message: error.message,
      hint: START_API_HINT,
      code: error.code,
    };
  }
  if (error.code === "database_unavailable" || error.status === 503) {
    return {
      title: "Database unavailable",
      message: error.message,
      hint: START_DB_HINT,
      code: error.code,
    };
  }
  if (error.status === 404) {
    return { title: "Not found", message: error.message, code: error.code };
  }
  return { title: "Request failed", message: error.message, code: error.code };
}
