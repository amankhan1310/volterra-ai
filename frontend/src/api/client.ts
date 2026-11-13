import createClient from "openapi-fetch";
import type { paths } from "./schema";

/**
 * Typed client for the FastAPI backend. Paths, parameters and response bodies are checked at
 * compile time against the generated contract. Requests go to the page's own origin; the Vite
 * dev/preview server proxies `/api` to the backend (see vite.config.ts).
 */
export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  // Resolve fetch per call so test tooling (MSW) that patches globalThis.fetch is honoured.
  fetch: (input) => globalThis.fetch(input),
});

/** An API failure normalised from the backend's `{"error": {code, message, details}}` envelope. */
export class ApiError extends Error {
  /** HTTP status; `0` when the API could not be reached at all. */
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Builds an error from a non-2xx response body (the API's envelope, or anything else). */
  static fromResponse(status: number, body: unknown): ApiError {
    const envelope = readEnvelope(body);
    if (envelope)
      return new ApiError(
        status,
        envelope.code,
        envelope.message,
        envelope.details,
      );
    // No envelope: the response did not come from the VOLTERRA API (e.g. the dev proxy answering
    // because the backend is down).
    if (status >= 500) return unreachable(status);
    return new ApiError(
      status,
      `http_${status}`,
      `Request failed with HTTP ${status}.`,
    );
  }
}

export const UNREACHABLE_MESSAGE = "The VOLTERRA API could not be reached.";

function unreachable(status: number, cause?: unknown): ApiError {
  return new ApiError(
    status,
    "api_unreachable",
    UNREACHABLE_MESSAGE,
    undefined,
    { cause },
  );
}

function readEnvelope(
  body: unknown,
): { code: string; message: string; details: unknown } | null {
  if (typeof body !== "object" || body === null || !("error" in body))
    return null;
  const error: unknown = body.error;
  if (typeof error !== "object" || error === null) return null;
  if (!("code" in error) || !("message" in error)) return null;
  const { code, message } = error;
  if (typeof code !== "string" || typeof message !== "string") return null;
  return {
    code,
    message,
    details: "details" in error ? error.details : undefined,
  };
}

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Runs an openapi-fetch call and returns its data, or throws an {@link ApiError}. */
export async function request<T>(
  call: () => Promise<FetchResult<T>>,
): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await call();
  } catch (cause) {
    throw unreachable(0, cause);
  }
  const { data, error, response } = result;
  if (!response.ok || error !== undefined)
    throw ApiError.fromResponse(response.status, error);
  return data as T;
}
