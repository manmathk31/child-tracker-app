/*
 * ChildTrack - Testing Portal: Master ESP (Guardian Scanner + Cloud Bridge)
 * 
 * Instructions:
 * 1. Open Arduino IDE -> Sketch -> Include Library -> Manage Libraries...
 *    Make sure "PubSubClient" (by Nick O'Leary) is installed.
 * 2. Flash this code onto ESP #2 (Master ESP) connected via USB to PC.
 * 3. Open Serial Monitor at 115200 baud to observe live Master-Slave proximity scans!
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <math.h>

// ==============================================================================
// 1. Wi-Fi Configuration
// ==============================================================================
const char* WIFI_SSID        = "MITAOE";
const char* WIFI_PASSWORD    = "MitAOE#2";

// ==============================================================================
// 2. HiveMQ Cloud MQTT Configuration (Pre-configured)
// ==============================================================================
const char* MQTT_BROKER      = "bba750cd4da045959dd983b09d38b17f.s1.eu.hivemq.cloud";
const int   MQTT_PORT        = 8883;
const char* MQTT_USER        = "inhousechildtracker";
const char* MQTT_PASSWORD    = "childtracker@123";
const char* TOPIC_TETHER     = "childtrack/testing/tether";

// ==============================================================================
// 3. Proximity Tether Configuration
// ==============================================================================
const char* TARGET_BEACON    = "CT-SLAVE-TAG";
const char* MASTER_ID        = "MASTER-01";
const char* SLAVE_ID         = "SLAVE-01";

// Proximity Warning and Alert Thresholds (dBm)
const int WARNING_RSSI       = -72; // Drifting far (~5-7m)
const int ALERT_RSSI         = -83; // Out of safe range (~12m+)

WiFiClientSecure espClient;
PubSubClient     mqttClient(espClient);

float calculateDistance(int rssi) {
  if (rssi == 0) return -1.0;
  float ratio = (-45.0 - (float)rssi) / (10.0 * 2.4);
  return round(pow(10.0, ratio) * 10.0) / 10.0;
}

void ensureMqttConnected() {
  while (!mqttClient.connected()) {
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[Wi-Fi] Reconnecting...");
      WiFi.reconnect();
      while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
      }
      Serial.println("\n[Wi-Fi] Reconnected!");
    }
    Serial.print("[Cloud MQTT] Connecting Master to HiveMQ Cloud...");
    String clientId = "ChildTrackMaster-" + String(random(0xffff), HEX);
    if (mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD)) {
      Serial.println(" CONNECTED!");
    } else {
      Serial.printf(" FAILED (rc=%d). Retrying in 3s...\n", mqttClient.state());
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n========================================================");
  Serial.println("  ChildTrack Tether Lab - Master ESP (Scanner + Cloud)  ");
  Serial.println("========================================================");

  // 1. Connect to Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  Serial.printf("[Wi-Fi] Connecting to '%s'", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[Wi-Fi] Connected successfully!");

  // 2. Configure Secure MQTT over TLS
  espClient.setInsecure();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  ensureMqttConnected();

  Serial.println("[Master] Proximity Guardian Engine ready and running!");
}

void loop() {
  if (!mqttClient.connected()) {
    ensureMqttConnected();
  }
  mqttClient.loop();

  // 1. Scan Wi-Fi radio frequencies to locate Slave Beacon
  Serial.println("\n[Scanner] Scanning for Slave beacon ('CT-SLAVE-TAG')...");
  int n = WiFi.scanNetworks(false, false); // synchronous scan
  
  bool slaveDetected = false;
  int lastSeenRSSI = 0;

  for (int i = 0; i < n; i++) {
    if (WiFi.SSID(i) == TARGET_BEACON) {
      slaveDetected = true;
      lastSeenRSSI = WiFi.RSSI(i);
      Serial.printf("  [BEACON DETECTED] Found Slave ESP! Signal RSSI: %d dBm\n", lastSeenRSSI);
      break;
    }
  }
  WiFi.scanDelete(); // Free scan memory

  // 2. Determine Proximity Status
  String statusStr;
  float dist = -1.0;

  if (slaveDetected) {
    dist = calculateDistance(lastSeenRSSI);
    if (lastSeenRSSI >= WARNING_RSSI) {
      statusStr = "SAFE";
      Serial.printf("[Status] 🟢 SAFE RANGE (~%.1fm | %d dBm)\n", dist, lastSeenRSSI);
    } else if (lastSeenRSSI >= ALERT_RSSI) {
      statusStr = "WARNING";
      Serial.printf("[Status] 🟡 WARNING: SLAVE DRIFTING FAR (~%.1fm | %d dBm)\n", dist, lastSeenRSSI);
    } else {
      statusStr = "LOST";
      Serial.printf("[Status] 🔴 CRITICAL: OUT OF RANGE (~%.1fm | %d dBm)\n", dist, lastSeenRSSI);
    }
  } else {
    statusStr = "LOST";
    Serial.println("[Status] 🚨 CRITICAL: SLAVE BEACON NOT DETECTED (LOST)!");
  }

  // 3. Construct JSON Payload
  String payload = "{";
  payload += "\"master_id\":\"" + String(MASTER_ID) + "\",";
  payload += "\"slave_id\":\"" + String(SLAVE_ID) + "\",";
  if (slaveDetected) {
    payload += "\"rssi\":" + String(lastSeenRSSI) + ",";
    payload += "\"distance_approx_m\":" + String(dist, 1) + ",";
  } else {
    payload += "\"rssi\":null,";
    payload += "\"distance_approx_m\":null,";
  }
  payload += "\"status\":\"" + statusStr + "\",";
  payload += "\"battery_master\":98,";
  payload += "\"battery_slave\":92";
  payload += "}";

  // 4. Publish live tether state to HiveMQ Cloud
  bool pub = mqttClient.publish(TOPIC_TETHER, payload.c_str());
  if (pub) {
    Serial.printf("[Cloud MQTT] Published tether state to '%s'\n", TOPIC_TETHER);
  } else {
    Serial.println("[Cloud MQTT] Failed to publish telemetry.");
  }

  // Small delay before next scan cycle
  delay(1500);
}
