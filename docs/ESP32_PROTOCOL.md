# ChildTrack ESP32 Hardware Protocol Specification

This document defines the communication contract between ESP32 wearable hardware tags and the ChildTrack backend platform.

---

## 1. Overview & Transport

ChildTrack supports dual ingestion transports:

### 1.1 Cloud MQTT (Recommended — Firewall & Network Isolation Proof)
- **Transport**: MQTT over TLS (Port 8883)
- **Broker**: HiveMQ Cloud (`*.hivemq.cloud`)
- **Telemetry Topic (Publish)**: `childtrack/telemetry`
- **Acknowledgement Topic (Subscribe)**: `childtrack/ack/{device_id}`
- **Authentication**: Username & Password credentials
- **Advantage**: Requires zero incoming ports on host machine; works across separate Wi-Fi networks and mobile hotspots.

### 1.2 Local HTTP Ingestion (Direct LAN)
- **Transport**: HTTP/1.1 POST over standard TLS/HTTPS (or HTTP for local isolated Wi-Fi networks).
- **Endpoint**: `/api/v1/tracking/ingest`
- **Content-Type**: `application/json`
- **Rate Limit**: Typically 1 transmission per wearable every 3 to 10 seconds (adaptive based on movement).

---

## 2. Telemetry Ingestion Payload

```json
{
  "device_id": "WB-001",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "battery_percent": 88,
  "firmware_version": "v1.2.0",
  "scan": [
    {
      "bssid": "24:F5:A2:33:44:01",
      "rssi": -52,
      "channel": 1
    },
    {
      "bssid": "24:F5:A2:33:44:02",
      "rssi": -71,
      "channel": 6
    },
    {
      "bssid": "24:F5:A2:33:44:03",
      "rssi": -85,
      "channel": 11
    }
  ],
  "events": {
    "sos_button_pressed": false,
    "fall_detected": false
  }
}
```

### Field Definitions
- `device_id` (string, required): Hardware identifier etched on casing.
- `mac_address` (string, required): Hardware Wi-Fi MAC address format `XX:XX:XX:XX:XX:XX`.
- `battery_percent` (integer, required): 0 to 100 percentage.
- `firmware_version` (string, optional): Installed device firmware version.
- `scan` (array of objects, required): Wi-Fi access points detected in last passive/active scan.
  - `bssid` (string, required): Access point BSSID.
  - `rssi` (integer, required): Signal strength in dBm (-100 to 0).
  - `channel` (integer, optional): Wi-Fi channel (1-14).
- `events` (object, optional): Hardware interrupt flags for emergency triggers.

---

## 3. Ingestion Acknowledgement Response

### 3.1 Success Response (`200 OK`)
```json
{
  "status": "ack",
  "device_id": "WB-001",
  "assigned_zone": "Classroom 3A",
  "confidence": 0.88,
  "server_time": "2026-09-17T00:00:00.000000Z"
}
```

### 3.2 Error Responses
- `400 Bad Request`: Malformed JSON or invalid data types.
- `404 Not Found`: Unregistered device MAC or identifier.
- `422 Unprocessable Entity`: Out of range RSSI or battery metrics.
- `429 Too Many Requests`: Rate limit exceeded.
