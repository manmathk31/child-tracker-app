"""Unit and integration tests for HiveMQ Cloud MQTT telemetry ingestion service."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.schemas.location import TelemetryIngestIn, TelemetryIngestResponse
from app.services import mqtt_service


@pytest.mark.asyncio
async def test_process_telemetry_payload_success(db_session: AsyncSession) -> None:
    """Verify that a valid telemetry packet is processed and ACK is published."""
    payload_data = {
        "device_id": "TEST-TAG-01",
        "mac_address": "AA:BB:CC:DD:EE:01",
        "battery_percent": 92,
        "firmware_version": "2.0.0-cloud",
        "scan": [
            {"bssid": "00:11:22:33:44:55", "rssi": -65, "channel": 1},
        ],
        "events": {"sos": False},
    }
    payload = TelemetryIngestIn.model_validate(payload_data)

    mock_ack = TelemetryIngestResponse(
        status="ack",
        device_id="TEST-TAG-01",
        assigned_zone="Classroom A",
        confidence=0.91,
    )

    with patch(
        "app.services.localization_service.process_telemetry_scan",
        new_callable=AsyncMock,
        return_value=mock_ack,
    ) as mock_localize, patch(
        "app.services.mqtt_service._publish_ack_message"
    ) as mock_pub_ack:
        await mqtt_service._process_telemetry_payload(payload)

        mock_localize.assert_awaited_once()
        mock_pub_ack.assert_called_once_with("childtrack/ack/TEST-TAG-01", mock_ack)


@pytest.mark.asyncio
async def test_process_telemetry_unknown_device_handled_safely() -> None:
    """Verify that an unregistered device is handled safely without raising unhandled errors."""
    payload_data = {
        "device_id": "UNKNOWN-TAG",
        "mac_address": "00:00:00:00:00:00",
        "battery_percent": 50,
        "scan": [{"bssid": "00:11:22:33:44:55", "rssi": -70}],
    }
    payload = TelemetryIngestIn.model_validate(payload_data)

    with patch(
        "app.services.localization_service.process_telemetry_scan",
        new_callable=AsyncMock,
        side_effect=NotFoundError("Device", "UNKNOWN-TAG"),
    ):
        # Must not raise an exception
        await mqtt_service._process_telemetry_payload(payload)


def test_on_message_valid_json() -> None:
    """Verify _on_message correctly validates JSON and dispatches async coroutine."""
    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    mock_loop.is_closed.return_value = False

    mqtt_service._event_loop = mock_loop

    mock_msg = MagicMock()
    mock_msg.topic = "childtrack/telemetry"
    mock_msg.payload = json.dumps(
        {
            "device_id": "TEST-TAG-02",
            "mac_address": "11:22:33:44:55:66",
            "battery_percent": 80,
            "scan": [{"bssid": "AA:BB:CC:DD:EE:FF", "rssi": -55}],
        }
    ).encode("utf-8")

    with patch("asyncio.run_coroutine_threadsafe") as mock_dispatch:
        mqtt_service._on_message(client=MagicMock(), userdata=None, msg=mock_msg)
        mock_dispatch.assert_called_once()


def test_on_message_malformed_json_discarded_gracefully() -> None:
    """Verify _on_message discards malformed JSON payloads without crashing."""
    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    mock_loop.is_closed.return_value = False
    mqtt_service._event_loop = mock_loop

    mock_msg = MagicMock()
    mock_msg.topic = "childtrack/telemetry"
    mock_msg.payload = b"this-is-not-json"

    with patch("asyncio.run_coroutine_threadsafe") as mock_dispatch:
        mqtt_service._on_message(client=MagicMock(), userdata=None, msg=mock_msg)
        mock_dispatch.assert_not_called()


def test_mqtt_service_disabled_skipped() -> None:
    """Verify start_mqtt_service exits immediately when MQTT_ENABLED is False."""
    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)

    with patch("app.services.mqtt_service.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.MQTT_ENABLED = False
        mock_get_settings.return_value = mock_settings

        mqtt_service.start_mqtt_service(mock_loop)
        assert mqtt_service._mqtt_client is None
