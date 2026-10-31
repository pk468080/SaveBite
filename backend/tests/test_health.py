from app.routers import health


def test_liveness_needs_no_supabase(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "savebite-api"
    assert "X-Request-Id" in response.headers


def test_readiness_ready_when_auth_ok(client, monkeypatch):
    async def _ok(url: str) -> bool:
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
    async def _down(url: str) -> bool:
        return False

    async def _pg_ok(url: str, key: str) -> bool:
        return True

    monkeypatch.setattr(health, "check_supabase_auth_health", _down)
    monkeypatch.setattr(health, "check_supabase_postgrest_health", _pg_ok)
    response = client.get("/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_readiness_degraded_when_postgrest_down(client, monkeypatch):
    async def _ok(url: str) -> bool:
        return True

    async def _pg_down(url: str, key: str) -> bool:
        return False

    monkeypatch.setattr(health, "check_supabase_auth_health", _ok)
    monkeypatch.setattr(health, "check_supabase_postgrest_health", _pg_down)
    response = client.get("/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
