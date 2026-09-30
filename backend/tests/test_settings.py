"""Automated tests for School and Safety Alert Settings models, services, REST API, and web views."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.settings import AlertSettingsUpdate, SchoolSettingsUpdate
from app.services import settings_service


@pytest.mark.asyncio
async def test_settings_service_defaults_and_updates(db_session: AsyncSession) -> None:
    """Verify singleton initialization and updates for school and alert settings."""
    # 1. School settings initialize with default values
    school = await settings_service.get_or_create_school_settings(db_session)
    assert school.id is not None
    assert school.school_name == "ChildTrack Academy"

    # Update school settings
    updated_school = await settings_service.update_school_settings(
        db_session,
        SchoolSettingsUpdate(school_name="Springfield Elementary", timezone="America/Chicago"),
    )
    assert updated_school.school_name == "Springfield Elementary"
    assert updated_school.timezone == "America/Chicago"

    # 2. Alert settings initialize with default values
    alerts = await settings_service.get_or_create_alert_settings(db_session)
    assert alerts.id is not None
    assert alerts.offline_threshold_minutes > 0

    # Update alert settings
    updated_alerts = await settings_service.update_alert_settings(
        db_session,
        AlertSettingsUpdate(offline_threshold_minutes=15, low_battery_percent=25),
    )
    assert updated_alerts.offline_threshold_minutes == 15
    assert updated_alerts.low_battery_percent == 25


@pytest.mark.asyncio
async def test_settings_api_endpoints(
    client: AsyncClient, admin_headers: dict, teacher_headers: dict
) -> None:
    """Verify REST API authorization and update operations on /api/v1/settings/*."""
    # 1. School settings: Teacher can view, cannot edit
    resp = await client.get("/api/v1/settings/school", headers=teacher_headers)
    assert resp.status_code == 200

    resp = await client.put(
        "/api/v1/settings/school",
        headers=teacher_headers,
        json={"school_name": "Teacher Renamed School"},
    )
    assert resp.status_code == 403

    # Admin can edit school settings
    resp = await client.put(
        "/api/v1/settings/school",
        headers=admin_headers,
        json={"school_name": "St. Jude Primary School"},
    )
    assert resp.status_code == 200
    assert resp.json()["school_name"] == "St. Jude Primary School"

    # 2. Alert settings: Teacher can view, cannot edit
    resp = await client.get("/api/v1/settings/alerts", headers=teacher_headers)
    assert resp.status_code == 200

    resp = await client.put(
        "/api/v1/settings/alerts",
        headers=teacher_headers,
        json={"offline_threshold_minutes": 20},
    )
    assert resp.status_code == 403

    # Admin can edit alert settings
    resp = await client.put(
        "/api/v1/settings/alerts",
        headers=admin_headers,
        json={"offline_threshold_minutes": 12, "low_battery_percent": 18},
    )
    assert resp.status_code == 200
    assert resp.json()["offline_threshold_minutes"] == 12
    assert resp.json()["low_battery_percent"] == 18


@pytest.mark.asyncio
async def test_settings_web_views(client: AsyncClient, admin_user, teacher_user) -> None:
    """Verify HTML web views and forms for system settings."""
    from app.core.security import create_access_token

    # Teacher cannot access settings page (redirects to /dashboard)
    teacher_token = create_access_token(subject=str(teacher_user.id), role=teacher_user.role.value)
    resp = await client.get(
        "/settings", cookies={"access_token": teacher_token}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"

    # Admin can access settings page
    admin_token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    admin_cookies = {"access_token": admin_token}
    resp = await client.get("/settings", cookies=admin_cookies)
    assert resp.status_code == 200
    assert "System Settings" in resp.text
    assert "Organization &amp; Safety Settings" in resp.text
