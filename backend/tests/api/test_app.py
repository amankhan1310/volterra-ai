"""App factory, settings, error envelope and the health endpoint."""

from __future__ import annotations

import pytest
from fastapi import APIRouter

from app.core.config import API_VERSION, Settings
from app.core.errors import ApiError
from app.main import create_app
from tests.support.api import client_for, make_settings

pytestmark = pytest.mark.anyio

SECRET_URL = "postgresql+asyncpg://user:s3cr3t-pa55@localhost:5432/db"


class FakeDatabase:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def ping(self) -> float:
        if self.fail:
            raise ConnectionRefusedError("host=localhost password=s3cr3t-pa55")
        return 1.5


async def test_health_without_database_reports_not_configured() -> None:
    async with client_for(create_app(make_settings())) as client:
        r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "service": "volterra-api",
        "version": API_VERSION,
        "api_version": "v1",
        "algorithm_version": "v1",
        "database": {"status": "not_configured", "latency_ms": None, "error": None},
    }


async def test_health_reports_database_separately_from_application() -> None:
    app = create_app(make_settings())
    app.state.database = FakeDatabase()
    async with client_for(app) as client:
        ok = (await client.get("/api/v1/health")).json()
    app.state.database = FakeDatabase(fail=True)
    async with client_for(app) as client:
        down = await client.get("/api/v1/health")
    assert ok["database"] == {"status": "ok", "latency_ms": 1.5, "error": None}
    assert down.status_code == 200 and down.json()["status"] == "ok"
    assert down.json()["database"] == {
        "status": "unavailable",
        "latency_ms": None,
        "error": "ConnectionRefusedError",
    }
    assert "s3cr3t" not in down.text


async def test_unknown_route_and_method_use_the_error_envelope() -> None:
    async with client_for(create_app(make_settings())) as client:
        missing = await client.get("/api/v1/nope")
        wrong = await client.post("/api/v1/health")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert wrong.status_code == 405
    assert wrong.json()["error"]["code"] == "method_not_allowed"


async def test_api_validation_and_unexpected_errors_use_the_envelope() -> None:
    app = create_app(make_settings())
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("leaky details s3cr3t-pa55")

    @router.get("/teapot")
    async def teapot() -> None:
        raise ApiError(418, "teapot", "I am a teapot", [{"hint": "tea"}])

    @router.get("/typed")
    async def typed(n: int) -> int:
        return n

    app.include_router(router, prefix="/test")
    async with client_for(app, raise_app_exceptions=False) as client:
        boom_r = await client.get("/test/boom")
        tea_r = await client.get("/test/teapot")
        typed_r = await client.get("/test/typed", params={"n": "x"})
    assert boom_r.status_code == 500
    assert boom_r.json() == {
        "error": {"code": "internal_error", "message": "Internal server error"}
    }
    assert "s3cr3t" not in boom_r.text
    assert tea_r.status_code == 418
    assert tea_r.json() == {
        "error": {"code": "teapot", "message": "I am a teapot", "details": [{"hint": "tea"}]}
    }
    assert typed_r.status_code == 422
    body = typed_r.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"][0]["loc"] == ["query", "n"]


async def test_cors_allows_configured_origin_only() -> None:
    app = create_app(make_settings(cors_origins="http://localhost:5173, http://example.test"))
    async with client_for(app) as client:
        allowed = await client.get("/api/v1/health", headers={"Origin": "http://example.test"})
        denied = await client.get("/api/v1/health", headers={"Origin": "http://evil.test"})
    assert allowed.headers["access-control-allow-origin"] == "http://example.test"
    assert "access-control-allow-origin" not in denied.headers


async def test_lifespan_runs_and_openapi_is_served() -> None:
    app = create_app(make_settings())
    async with app.router.lifespan_context(app), client_for(app) as client:
        spec = (await client.get("/api/v1/openapi.json")).json()
    assert spec["info"]["title"] == "VOLTERRA AI API"
    assert "/api/v1/health" in spec["paths"]


def test_settings_never_expose_the_database_password() -> None:
    settings = make_settings(database_url=SECRET_URL)
    assert "s3cr3t" not in repr(settings)
    assert "s3cr3t" not in str(settings.model_dump())
    assert settings.database_dsn() == SECRET_URL
    assert make_settings().database_dsn() is None


def test_settings_read_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOLTERRA_ENV", "production")
    monkeypatch.setenv("VOLTERRA_CORS_ORIGINS", "http://a.test,,http://b.test")
    monkeypatch.setenv("VOLTERRA_ANALYSIS_CACHE_SIZE", "8")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.environment == "production"
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]
    assert settings.analysis_cache_size == 8
