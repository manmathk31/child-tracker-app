"""Testing Portal Service: Master-Slave ESP Proximity & Tether Alert State Machine.

Maintains real-time in-memory tracking of Master and Slave ESP proximity,
computes threshold breaches, manages separation alerts, and feeds the Testing Portal UI.
"""

import collections
import logging
import math
from datetime import UTC, datetime
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("childtrack.testing_tether")

# Default thresholds
DEFAULT_WARNING_RSSI = -75  # dBm (Approaching outer boundary)
DEFAULT_ALERT_RSSI = -85    # dBm (Beyond safe separation distance)
WATCHDOG_TIMEOUT_SECONDS = 5.0  # If no beacon for > 5s, mark as LOST


class TetherMonitor:
    """In-memory state monitor for Master-Slave ESP proximity testing."""

    def __init__(self) -> None:
        self.master_id: str = "MASTER-01"
        self.slave_id: str = "SLAVE-01"
        self.rssi: Optional[int] = None
        self.distance_m: Optional[float] = None
        self.status: str = "LOST"  # 'SAFE', 'WARNING', 'LOST'
        self.battery_master: Optional[int] = None
        self.battery_slave: Optional[int] = None
        self.last_seen_at: Optional[datetime] = None
        self.alert_active: bool = False
        self.alert_message: str = "Waiting for initial ESP32 telemetry..."
        
        # Configurable alert threshold
        self.warning_threshold: int = DEFAULT_WARNING_RSSI
        self.alert_threshold: int = DEFAULT_ALERT_RSSI

        # Circular buffer for live RSSI history chart (last 50 readings)
        self.history: Deque[Dict[str, Any]] = collections.deque(maxlen=50)

    def calculate_approx_distance(self, rssi: int, tx_power: int = -59) -> float:
        """Estimate distance in meters from BLE RSSI using log-distance path loss formula."""
        if rssi == 0:
            return -1.0
        ratio = (tx_power - rssi) / (10.0 * 2.5)  # path-loss exponent ~2.5 for indoor/crowded
        return round(math.pow(10.0, ratio), 1)

    def update_telemetry(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update monitor state from incoming MQTT tether packet."""
        now = datetime.now(UTC)
        self.last_seen_at = now

        self.master_id = str(data.get("master_id", self.master_id))
        self.slave_id = str(data.get("slave_id", self.slave_id))
        raw_rssi = data.get("rssi")

        if raw_rssi is not None and isinstance(raw_rssi, (int, float)) and raw_rssi != 0:
            self.rssi = int(raw_rssi)
            self.distance_m = data.get("distance_approx_m") or self.calculate_approx_distance(self.rssi)

            if self.rssi >= self.warning_threshold:
                self.status = "SAFE"
                self.alert_active = False
                self.alert_message = f"Slave is within safe range ({self.rssi} dBm, ~{self.distance_m}m)"
            elif self.rssi >= self.alert_threshold:
                self.status = "WARNING"
                self.alert_active = True
                self.alert_message = f"Warning: Slave is drifting away ({self.rssi} dBm, ~{self.distance_m}m)"
            else:
                self.status = "LOST"
                self.alert_active = True
                self.alert_message = f"DANGER: Slave is beyond safe perimeter! ({self.rssi} dBm, ~{self.distance_m}m)"
        else:
            # Master reported beacon not detected in recent scan
            self.rssi = None
            self.distance_m = None
            self.status = "LOST"
            self.alert_active = True
            self.alert_message = "CRITICAL ALERT: Slave beacon signal lost or out of range!"

        self.battery_master = data.get("battery_master", self.battery_master)
        self.battery_slave = data.get("battery_slave", self.battery_slave)

        snapshot = {
            "timestamp": now.strftime("%H:%M:%S"),
            "rssi": self.rssi,
            "distance_m": self.distance_m,
            "status": self.status,
            "alert": self.alert_active,
        }
        self.history.append(snapshot)
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """Return current real-time tether state with watchdog timeout evaluation."""
        now = datetime.now(UTC)

        # Watchdog: If last reading is older than WATCHDOG_TIMEOUT_SECONDS, mark as lost
        if self.last_seen_at is None:
            effective_status = "WAITING"
            effective_alert = False
            msg = "Waiting for Master ESP to connect..."
            seconds_ago = None
        else:
            diff = (now - self.last_seen_at).total_seconds()
            seconds_ago = round(diff, 1)
            if diff > WATCHDOG_TIMEOUT_SECONDS:
                effective_status = "LOST"
                effective_alert = True
                msg = f"SIGNAL LOST: No telemetry for {int(diff)}s!"
            else:
                effective_status = self.status
                effective_alert = self.alert_active
                msg = self.alert_message

        return {
            "master_id": self.master_id,
            "slave_id": self.slave_id,
            "rssi": self.rssi if effective_status != "LOST" else None,
            "distance_m": self.distance_m if effective_status != "LOST" else None,
            "status": effective_status,
            "alert_active": effective_alert,
            "alert_message": msg,
            "warning_threshold": self.warning_threshold,
            "alert_threshold": self.alert_threshold,
            "battery_master": self.battery_master or 100,
            "battery_slave": self.battery_slave or 100,
            "last_seen_seconds_ago": seconds_ago,
            "history": list(self.history),
        }

    def set_thresholds(self, warning_rssi: int, alert_rssi: int) -> None:
        """Update dynamic alert thresholds."""
        self.warning_threshold = warning_rssi
        self.alert_threshold = alert_rssi
        logger.info("Updated tether thresholds: Warning=%ddBm, Alert=%ddBm", warning_rssi, alert_rssi)


# Global singleton instance
_monitor = TetherMonitor()


def get_tether_monitor() -> TetherMonitor:
    """Return singleton monitor instance."""
    return _monitor
