"""Tests for application health check and base page rendering."""

from unittest.mock import patch
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_healthy(client: AsyncClient) -> None:
    """Verify that /health reports 200 and healthy status when database is available."""
    with patch("app.routers.health.check_db_connection", return_value=True):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "version" in data
        assert "timestamp" in data
        assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_health_check_degraded(client: AsyncClient) -> None:
    """Verify that /health reports 503 and degraded status when database is unavailable."""
    with patch("app.routers.health.check_db_connection", return_value=False):
        response = await client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"


@pytest.mark.asyncio
async def test_root_redirect_to_dashboard(client: AsyncClient) -> None:
    """Verify that accessing root '/' redirects to '/dashboard'."""
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


@pytest.mark.asyncio
async def test_dashboard_renders_empty_state(client: AsyncClient) -> None:
    """Verify that /dashboard renders HTML with genuine empty state and no fake data."""
    response = await client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html_content = response.text
    assert "Live Safety Dashboard" in html_content
    assert "data-testid=\"empty-state\"" in html_content
    assert "No zones configured yet" in html_content
