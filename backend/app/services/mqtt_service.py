"""HiveMQ Cloud MQTT Background Telemetry Ingestion Service.

Manages connection to HiveMQ Cloud MQTT broker over secure TLS (port 8883),
subscribes to ESP32 wearable telemetry topics, decodes JSON payloads,
and processes them asynchronously through the ChildTrack localization engine.
"""

import asyncio
import json
import logging
import uuid
from typing import Any

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.database.session import get_session_factory
from app.schemas.location import TelemetryIngestIn, TelemetryIngestResponse
from app.services import localization_service

logger = logging.getLogger("childtrack.mqtt")

_mqtt_client: Any = None
_is_connected: bool = False
_event_loop: asyncio.AbstractEventLoop | None = None


async def _process_telemetry_payload(payload: TelemetryIngestIn) -> None:
    """Asynchronously process an ingested telemetry packet in the DB context.

    Delegates to localization_service to update device online state,
    compute real-time indoor zone estimates, and persist location breadcrumbs.
    Optionally publishes an acknowledgement back to the device's cloud topic.

    Args:
        payload: Validated TelemetryIngestIn telemetry model.
    """
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            ack_response: TelemetryIngestResponse = (
                await localization_service.process_telemetry_scan(db, payload)
            )
            logger.info(
                "MQTT telemetry processed for device %s -> Zone: %s (confidence: %.2f)",
                payload.device_id,
                ack_response.assigned_zone or "Unassigned/LowConfidence",
                ack_response.confidence,
            )

            # Publish zone acknowledgement back to cloud for ESP32 tag
            settings = get_settings()
            ack_topic = f"{settings.MQTT_TOPIC_ACK_PREFIX}/{payload.device_id}"
            _publish_ack_message(ack_topic, ack_response)

        except NotFoundError:
            logger.warning(
                "MQTT telemetry ignored: Unrecognized or unregistered device code '%s'",
                payload.device_id,
            )
        except Exception as exc:
            logger.error(
                "Error processing MQTT telemetry for device %s: %s",
                payload.device_id,
                exc,
                exc_info=True,
            )


def _publish_ack_message(topic: str, ack: TelemetryIngestResponse) -> None:
    """Publish an ingestion acknowledgement packet back to the MQTT broker.

    Args:
        topic: The target MQTT topic (e.g. childtrack/ack/ESP32-TAG-01).
        ack: The TelemetryIngestResponse model containing zone estimate.
    """
    global _mqtt_client
    if _mqtt_client is None:
        return

    try:
        payload_json = json.dumps(
            {
                "status": ack.status,
                "device_id": ack.device_id,
                "assigned_zone": ack.assigned_zone,
                "confidence": ack.confidence,
                "server_time": ack.server_time.isoformat() if ack.server_time else None,
            }
        )
        _mqtt_client.publish(topic, payload_json, qos=0)
    except Exception as exc:
        logger.debug("Failed to publish zone acknowledgement to topic %s: %s", topic, exc)


def _on_connect(client: Any, userdata: Any, flags: Any, rc: Any, *args: Any) -> None:
    """Callback fired when the MQTT client establishes connection with broker."""
    global _is_connected
    settings = get_settings()

    # Support both paho-mqtt v1.x (rc is int) and v2.x (rc is ReasonCode)
    rc_code = getattr(rc, "value", rc)
    if rc_code == 0:
        _is_connected = True
        logger.info(
            "Successfully connected to HiveMQ Cloud MQTT broker at %s:%d",
            settings.MQTT_BROKER,
            settings.MQTT_PORT,
        )
        client.subscribe(settings.MQTT_TOPIC_TELEMETRY, qos=1)
        logger.info("Subscribed to MQTT telemetry topic: %s", settings.MQTT_TOPIC_TELEMETRY)
    else:
        _is_connected = False
        logger.error(
            "Failed to connect to HiveMQ Cloud broker (result code: %s). Check credentials and network.",
            str(rc),
        )


def _on_disconnect(client: Any, userdata: Any, rc: Any, *args: Any) -> None:
    """Callback fired when client loses connection to MQTT broker."""
    global _is_connected
    _is_connected = False
    logger.warning("Disconnected from HiveMQ Cloud MQTT broker (rc=%s). Auto-reconnecting...", str(rc))


def _on_message(client: Any, userdata: Any, msg: Any) -> None:
    """Callback fired when a message arrives on a subscribed MQTT topic."""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        logger.warning("Dropped incoming MQTT message: Event loop is inactive")
        return

    try:
        raw_payload = msg.payload.decode("utf-8")
        logger.debug("Received MQTT message on %s (%d bytes)", msg.topic, len(raw_payload))

        # Validate message schema with Pydantic
        payload_model = TelemetryIngestIn.model_validate_json(raw_payload)

        # Dispatch async DB processing task onto FastAPI main event loop
        asyncio.run_coroutine_threadsafe(
            _process_telemetry_payload(payload_model),
            _event_loop,
        )

    except ValidationError as val_err:
        logger.warning(
            "Discarded invalid telemetry payload on %s: %s",
            msg.topic,
            val_err.errors(),
        )
    except Exception as exc:
        logger.warning("Error parsing incoming MQTT message on %s: %s", msg.topic, exc)


def start_mqtt_service(loop: asyncio.AbstractEventLoop) -> None:
    """Initialize and start the background HiveMQ Cloud MQTT subscriber.

    Safe startup: Checks configuration and paho-mqtt availability.
    If credentials or library are missing, logs guidance without crashing the app.

    Args:
        loop: Running asyncio event loop for scheduling database coroutines.
    """
    global _mqtt_client, _event_loop
    settings = get_settings()

    if not settings.MQTT_ENABLED:
        logger.info("HiveMQ Cloud MQTT service is disabled (MQTT_ENABLED=False).")
        return

    if not settings.MQTT_BROKER:
        logger.info("HiveMQ Cloud broker is not configured (MQTT_BROKER is empty). Skipping MQTT startup.")
        return

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.warning(
            "paho-mqtt package is not installed. To enable HiveMQ Cloud telemetry, "
            "install dependencies using: pip install -r requirements.txt"
        )
        return

    _event_loop = loop

    try:
        client_id = f"ChildTrackBackend-{uuid.uuid4().hex[:8]}"

        # Support both paho-mqtt v2 and v1 constructor
        try:
            from paho.mqtt.enums import CallbackAPIVersion

            client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=client_id)
        except (ImportError, AttributeError):
            client = mqtt.Client(client_id=client_id)

        # Configure secure TLS connection (required for HiveMQ Cloud port 8883)
        if settings.MQTT_PORT in (8883, 8884):
            client.tls_set()

        # Set user authentication credentials
        if settings.MQTT_USERNAME:
            client.username_pw_set(
                username=settings.MQTT_USERNAME,
                password=settings.MQTT_PASSWORD or "",
            )

        client.on_connect = _on_connect
        client.on_disconnect = _on_disconnect
        client.on_message = _on_message

        # Non-blocking connection and background event loop thread
        logger.info(
            "Initiating connection to HiveMQ Cloud broker: %s:%d (user: %s)...",
            settings.MQTT_BROKER,
            settings.MQTT_PORT,
            settings.MQTT_USERNAME or "none",
        )
        client.connect_async(
            host=settings.MQTT_BROKER,
            port=settings.MQTT_PORT,
            keepalive=settings.MQTT_KEEPALIVE,
        )
        client.loop_start()
        _mqtt_client = client

    except Exception as exc:
        logger.error(
            "Failed to start HiveMQ Cloud MQTT client: %s. Local HTTP endpoints remain active.",
            exc,
            exc_info=True,
        )


def stop_mqtt_service() -> None:
    """Gracefully disconnect and terminate the background MQTT client thread."""
    global _mqtt_client, _is_connected, _event_loop
    if _mqtt_client is not None:
        try:
            logger.info("Stopping HiveMQ Cloud MQTT client...")
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
        except Exception as exc:
            logger.warning("Error during MQTT client shutdown: %s", exc)
        finally:
            _mqtt_client = None
            _is_connected = False
            _event_loop = None


def is_mqtt_connected() -> bool:
    """Return True if the MQTT client is currently connected to the broker."""
    return _is_connected
