import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../app/queryClient";
import { apiError, fixtures, server } from "../test/msw";
import { ApiError, api, request } from "./client";
import { START_API_HINT, START_DB_HINT, describeError } from "./errors";

describe("request", () => {
  it("returns the response data", async () => {
    const health = await request(() => api.GET("/api/v1/health"));
    expect(health).toEqual(fixtures.health);
  });

  it("normalises the API error envelope", async () => {
    server.use(
      http.get("*/api/v1/batteries", () =>
        apiError(503, "database_unavailable", "The database is not configured"),
      ),
    );
    const error = await request(() => api.GET("/api/v1/batteries")).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 503,
      code: "database_unavailable",
      message: "The database is not configured",
    });
  });

  it("treats a 5xx without the envelope as an unreachable API (dev proxy, backend down)", async () => {
    server.use(
      http.get("*/api/v1/health", () => new HttpResponse("", { status: 500 })),
    );
    await expect(
      request(() => api.GET("/api/v1/health")),
    ).rejects.toMatchObject({
      status: 500,
      code: "api_unreachable",
    });
  });

  it("reports a 4xx without the envelope by status", async () => {
    server.use(
      http.get(
        "*/api/v1/health",
        () => new HttpResponse("nope", { status: 418 }),
      ),
    );
    await expect(
      request(() => api.GET("/api/v1/health")),
    ).rejects.toMatchObject({
      status: 418,
      code: "http_418",
    });
  });

  it("reports a network failure as unreachable with status 0", async () => {
    server.use(http.get("*/api/v1/health", () => HttpResponse.error()));
    await expect(
      request(() => api.GET("/api/v1/health")),
    ).rejects.toMatchObject({
      status: 0,
      code: "api_unreachable",
    });
  });
});

describe("ApiError.fromResponse", () => {
  it.each([
    ["no body", undefined],
    ["null", null],
    ["string error", { error: "boom" }],
    ["null error", { error: null }],
    ["missing message", { error: { code: "x" } }],
    ["non-string fields", { error: { code: 1, message: 2 } }],
  ])("falls back when the envelope is malformed (%s)", (_label, body) => {
    expect(ApiError.fromResponse(400, body)).toMatchObject({
      status: 400,
      code: "http_400",
    });
  });

  it("keeps envelope details", () => {
    const details = [
      { loc: ["query", "eol_pct"], msg: "too big", type: "less_than_equal" },
    ];
    const error = ApiError.fromResponse(422, {
      error: {
        code: "validation_error",
        message: "Request validation failed",
        details,
      },
    });
    expect(error.details).toEqual(details);
    expect(error.name).toBe("ApiError");
  });
});

describe("describeError", () => {
  it("explains an unreachable API with the start command", () => {
    expect(
      describeError(new ApiError(0, "api_unreachable", "x")),
    ).toMatchObject({
      title: "API unreachable",
      hint: START_API_HINT,
    });
  });

  it("explains an unavailable database", () => {
    expect(
      describeError(new ApiError(503, "database_unavailable", "down")),
    ).toMatchObject({
      title: "Database unavailable",
      message: "down",
      hint: START_DB_HINT,
      code: "database_unavailable",
    });
  });

  it("reports not found and other API errors", () => {
    expect(
      describeError(new ApiError(404, "not_found", "Battery x not found"))
        .title,
    ).toBe("Not found");
    expect(
      describeError(new ApiError(422, "validation_error", "bad")).title,
    ).toBe("Request failed");
  });

  it("handles errors that did not come from the API", () => {
    expect(describeError(new Error("kaput"))).toEqual({
      title: "Unexpected error",
      message: "kaput",
    });
    expect(describeError("weird")).toEqual({
      title: "Unexpected error",
      message: "weird",
    });
  });
});

describe("query client retry policy", () => {
  const retry = createQueryClient().getDefaultOptions().queries?.retry as (
    n: number,
    e: unknown,
  ) => boolean;

  it("retries an unreachable API or a 5xx once", () => {
    expect(retry(0, new ApiError(0, "api_unreachable", "x"))).toBe(true);
    expect(retry(0, new ApiError(503, "database_unavailable", "x"))).toBe(true);
    expect(retry(1, new ApiError(503, "database_unavailable", "x"))).toBe(
      false,
    );
  });

  it("never retries client errors or non-API errors", () => {
    expect(retry(0, new ApiError(404, "not_found", "x"))).toBe(false);
    expect(retry(0, new Error("x"))).toBe(false);
  });
});
