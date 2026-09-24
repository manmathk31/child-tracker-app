"""Unit tests for Testing Portal Master-Slave ESP proximity state machine."""

import time
from datetime import UTC, datetime, timedelta

from app.services.testing_tether_service import TetherMonitor


def test_tether_monitor_safe_proximity() -> None:
    """Verify that strong RSSI is categorized as SAFE without alarms."""
    monitor = TetherMonitor()
    payload = {
        "master_id": "MASTER-01",
        "slave_id": "SLAVE-01",
        "rssi": -60,  # Strong signal
        "battery_master": 95,
        "battery_slave": 90,
    }
    status = monitor.update_telemetry(payload)
    assert status["status"] == "SAFE"
    assert status["alert_active"] is False
    assert status["rssi"] == -60
    assert status["distance_m"] is not None
    assert status["distance_m"] < 3.0


def test_tether_monitor_warning_proximity() -> None:
    """Verify that intermediate RSSI triggers a WARNING drift alert."""
    monitor = TetherMonitor()
    payload = {
        "master_id": "MASTER-01",
        "slave_id": "SLAVE-01",
        "rssi": -80,  # Drifting between -75 and -85
    }
    status = monitor.update_telemetry(payload)
    assert status["status"] == "WARNING"
    assert status["alert_active"] is True
    assert "Warning" in status["alert_message"]


def test_tether_monitor_out_of_range_alert() -> None:
    """Verify that weak RSSI or lost beacon triggers critical LOST alert."""
    monitor = TetherMonitor()
    payload = {
        "master_id": "MASTER-01",
        "slave_id": "SLAVE-01",
        "rssi": -92,  # Very weak signal
    }
    status = monitor.update_telemetry(payload)
    assert status["status"] == "LOST"
    assert status["alert_active"] is True


def test_tether_watchdog_timeout() -> None:
    """Verify that watchdog marks status as LOST if no telemetry arrives within 5 seconds."""
    monitor = TetherMonitor()
    # Simulate reading from 10 seconds ago
    monitor.last_seen_at = datetime.now(UTC) - timedelta(seconds=10)
    monitor.status = "SAFE"
    monitor.alert_active = False

    status = monitor.get_status()
    assert status["status"] == "LOST"
    assert status["alert_active"] is True
    assert "SIGNAL LOST" in status["alert_message"]


def test_tether_dynamic_threshold_update() -> None:
    """Verify threshold customization affects state classification."""
    monitor = TetherMonitor()
    monitor.set_thresholds(warning_rssi=-70, alert_rssi=-80)

    # -72 dBm would have been SAFE with default -75, but should now be WARNING
    payload = {"master_id": "M1", "slave_id": "S1", "rssi": -72}
    status = monitor.update_telemetry(payload)
    assert status["status"] == "WARNING"
