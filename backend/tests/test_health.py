from pydantic import SecretStr

from app.config import Settings, get_settings
from app.routers import health


async def test_postgrest_check_sends_secret_key_header(monkeypatch):
    _RecordingAsyncClient.instances.clear()
    monkeypatch.setattr(health.httpx, "AsyncClient", _RecordingAsyncClient)
    ok = await health.check_supabase_postgrest_health(
        "https://example.supabase.co", "test-secret-key"
    )
    assert ok is True
    ((url, headers),) = _RecordingAsyncClient.instances[0].calls
    assert url == "https://example.supabase.co/rest/v1/"
    assert headers == {"apikey": "test-secret-key"}


async def test_postgrest_check_reports_unhealthy_without_secret_key(
    monkeypatch,
):
    _RecordingAsyncClient.instances.clear()
    monkeypatch.setattr(health.httpx, "AsyncClient", _RecordingAsyncClient)
    assert (
        await health.check_supabase_postgrest_health(
            "https://example.supabase.co", None
        )
        is False
    )
    assert (
        await health.check_supabase_postgrest_health("https://example.supabase.co", "")
        is False
    )
    assert _RecordingAsyncClient.instances == []


def test_readiness_passes_service_role_key_to_postgrest_check(app, client, monkeypatch):
    seen: dict[str, str | None] = {}

    async def _auth_ok(url: str, key: str) -> bool:
        return True

    async def _pg_capture(url: str, key: str | None) -> bool:
        seen["key"] = key
        return True

    monkeypatch.setattr(health, "check_supabase_auth_health", _auth_ok)
    monkeypatch.setattr(health, "check_supabase_postgrest_health", _pg_capture)
    app.dependency_overrides[get_settings] = lambda: Settings(
        supabase_url="https://zehnhqcfawagxbactvne.supabase.co",
        supabase_publishable_key="test-publishable-key",
        supabase_service_role_key=SecretStr("test-secret-key"),
    )
    try:
        response = client.get("/v1/health/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert seen["key"] == "test-secret-key"


def test_liveness_needs_no_supabase(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "savebite-api"
    assert "X-Request-Id" in response.headers


def test_readiness_ready_when_auth_ok(client, monkeypatch):
    async def _ok(url: str, key: str) -> bool:
        return True

    async def _pg_ok(url: str, key: str) -> bool:
        return True

    monkeypatch.setattr(health, "check_supabase_auth_health", _ok)
    monkeypatch.setattr(health, "check_supabase_postgrest_health", _pg_ok)
    response = client.get("/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["supabase_auth"] == "ok"
    assert response.json()["checks"]["postgrest"] == "ok"
    # Readiness must never expose credentials, URLs, or keys.
    assert "supabase.co" not in response.text
    assert "test-publishable-key" not in response.text


def test_readiness_degraded_when_auth_down(client, monkeypatch):
    async def _down(url: str, key: str) -> bool:
        return False

    async def _pg_ok(url: str, key: str) -> bool:
        return True

    monkeypatch.setattr(health, "check_supabase_auth_health", _down)
    monkeypatch.setattr(health, "check_supabase_postgrest_health", _pg_ok)
    response = client.get("/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_readiness_degraded_when_postgrest_down(client, monkeypatch):
    async def _ok(url: str, key: str) -> bool:
        return True

    async def _pg_down(url: str, key: str) -> bool:
        return False

    monkeypatch.setattr(health, "check_supabase_auth_health", _ok)
    monkeypatch.setattr(health, "check_supabase_postgrest_health", _pg_down)
    response = client.get("/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_readiness_passes_publishable_key_to_auth_check(client, monkeypatch):
    seen: dict[str, str] = {}

    async def _capture(url: str, key: str) -> bool:
        seen["url"] = url
        seen["key"] = key
        return True

    async def _pg_ok(url: str, key: str) -> bool:
        return True

    monkeypatch.setattr(health, "check_supabase_auth_health", _capture)
    monkeypatch.setattr(health, "check_supabase_postgrest_health", _pg_ok)
    response = client.get("/v1/health/ready")
    assert response.status_code == 200
    assert seen["key"] == "test-publishable-key"


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _RecordingAsyncClient:
    instances: list["_RecordingAsyncClient"] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.calls: list[tuple[str, dict[str, str] | None]] = []
        _RecordingAsyncClient.instances.append(self)

    async def __aenter__(self) -> "_RecordingAsyncClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> _FakeResponse:
        self.calls.append((url, headers))
        return _FakeResponse(200)


async def test_auth_health_check_sends_apikey_header(monkeypatch):
    _RecordingAsyncClient.instances.clear()
    monkeypatch.setattr(health.httpx, "AsyncClient", _RecordingAsyncClient)
    ok = await health.check_supabase_auth_health(
        "https://example.supabase.co", "test-publishable-key"
    )
    assert ok is True
    ((url, headers),) = _RecordingAsyncClient.instances[0].calls
    assert url == "https://example.supabase.co/auth/v1/health"
    assert headers == {"apikey": "test-publishable-key"}


class _UnauthorizedAsyncClient(_RecordingAsyncClient):
    async def get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> _FakeResponse:
        self.calls.append((url, headers))
        return _FakeResponse(401)


async def test_auth_health_check_reports_unhealthy_on_401(monkeypatch):
    # Regression: the Supabase gateway answers keyless /auth/v1/*
    # requests with 401, so a 401 must mean unhealthy, never ready.
    monkeypatch.setattr(health.httpx, "AsyncClient", _UnauthorizedAsyncClient)
    ok = await health.check_supabase_auth_health(
        "https://example.supabase.co", "test-publishable-key"
    )
    assert ok is False


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
