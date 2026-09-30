/*
 * ChildTrack - ESP32 Child Wearable Hardware Tracker (Cloud MQTT Edition)
 * 
 * Instructions:
 * 1. Open Arduino IDE -> Sketch -> Include Library -> Manage Libraries...
 *    Search for "PubSubClient" (by Nick O'Leary) and click Install.
 * 2. Fill in your Wi-Fi credentials (WIFI_SSID & WIFI_PASSWORD).
 * 3. Enter your HiveMQ Cloud password for user "inhousechildtracker".
 * 4. Select board "ESP32 Dev Module" (or your specific ESP32) and port.
 * 5. Flash this code to your ESP32 and open Serial Monitor at 115200 baud!
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

// ==============================================================================
// 1. Wi-Fi Configuration (Any Wi-Fi or Mobile Hotspot works!)
// ==============================================================================
const char* WIFI_SSID        = "YOUR_WIFI_OR_HOTSPOT_NAME";
const char* WIFI_PASSWORD    = "YOUR_WIFI_PASSWORD";

// ==============================================================================
// 2. HiveMQ Cloud MQTT Configuration
// ==============================================================================
const char* MQTT_BROKER      = "bba750cd4da045959dd983b09d38b17f.s1.eu.hivemq.cloud";
const int   MQTT_PORT        = 8883; // Secure TLS port
const char* MQTT_USER        = "inhousechildtracker";
const char* MQTT_PASSWORD    = "YOUR_HIVEMQ_PASSWORD_HERE"; // Enter password you just set!

// MQTT Topics
const char* TOPIC_TELEMETRY  = "childtrack/telemetry";

// ==============================================================================
// 3. Device Identification
// ==============================================================================
// Device identifier registered in ChildTrack UI (/devices)
const char* DEVICE_ID        = "ESP32-TAG-01";
const char* FIRMWARE_VERSION = "2.0.0-cloud";

// Telemetry interval (milliseconds) - standard operational interval is 3000ms - 5000ms
const unsigned long TRACKING_INTERVAL_MS = 3500;

// Physical button pin (GPIO 0 is the built-in "BOOT" button on most ESP32 boards)
const int SOS_BUTTON_PIN     = 0; 

// Simulated battery level (set between 0 and 100)
int simulatedBatteryPercent  = 88;

// ==============================================================================
// Secure Client & MQTT Instance
// ==============================================================================
WiFiClientSecure espClient;
PubSubClient     mqttClient(espClient);

// Callback function to handle incoming cloud acknowledgements (Assigned Zone & Confidence)
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.printf("\n[Cloud ACK Received] Topic [%s]:\n  -> %s\n", topic, message.c_str());
}

// Connect or reconnect to HiveMQ Cloud MQTT Broker
void ensureMqttConnected() {
  while (!mqttClient.connected()) {
    Serial.print("[Cloud MQTT] Connecting to HiveMQ Cloud broker...");
    
    // Generate unique client ID to prevent broker collisions
    String clientId = "ChildTrackWearable-" + String(DEVICE_ID) + "-" + String(random(0xffff), HEX);
    
    if (mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD)) {
      Serial.println(" CONNECTED!");
      
      // Subscribe to personal device acknowledgement topic
      String ackTopic = "childtrack/ack/" + String(DEVICE_ID);
      mqttClient.subscribe(ackTopic.c_str());
      Serial.printf("[Cloud MQTT] Subscribed for live zone ACKs on: %s\n", ackTopic.c_str());
    } else {
      Serial.printf(" FAILED (rc=%d). Retrying in 3 seconds...\n", mqttClient.state());
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Configure onboard BOOT button as SOS trigger (Active LOW with internal pullup)
  pinMode(SOS_BUTTON_PIN, INPUT_PULLUP);

  Serial.println("\n========================================================");
  Serial.println("  ChildTrack ESP32 Wearable Tracker - HiveMQ Cloud Edition");
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
  Serial.printf("[Wi-Fi] ESP32 IP Address : %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("[Wi-Fi] ESP32 MAC Address: %s\n", WiFi.macAddress().c_str());
  Serial.printf("[Device] Device Code     : %s\n", DEVICE_ID);

  // 2. Configure Secure TLS MQTT
  // HiveMQ Cloud uses standard Let's Encrypt certificates. setInsecure() allows TLS handshake.
  espClient.setInsecure();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(onMqttMessage);
  
  // CRITICAL: Expand buffer from default 256 bytes to 2048 bytes for multi-AP scan payloads
  mqttClient.setBufferSize(2048);

  // Connect to cloud broker
  ensureMqttConnected();
}

void loop() {
  // Keep MQTT connection alive and process incoming packets
  if (!mqttClient.connected()) {
    ensureMqttConnected();
  }
  mqttClient.loop();

  // Check if SOS/BOOT button is pressed (LOW when pressed on GPIO 0)
  bool sosTriggered = (digitalRead(SOS_BUTTON_PIN) == LOW);
  if (sosTriggered) {
    Serial.println("\n>>> [EMERGENCY] SOS / PANIC BUTTON PRESSED! <<<");
  }

  // 1. Perform physical Wi-Fi radio scan
  Serial.println("\n[Scanner] Scanning environment Wi-Fi RSSI signals...");
  int n = WiFi.scanNetworks(false, true); // (async=false, show_hidden=true)

  if (n <= 0) {
    Serial.println("[Scanner] No Wi-Fi signals detected.");
    delay(TRACKING_INTERVAL_MS);
    return;
  }

  Serial.printf("[Scanner] Found %d APs. Packaging cloud payload...\n", n);

  // 2. Construct JSON payload conforming to ESP32_PROTOCOL.md & TelemetryIngestIn schema
  String jsonPayload = "{";
  jsonPayload += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  jsonPayload += "\"mac_address\":\"" + WiFi.macAddress() + "\",";
  jsonPayload += "\"battery_percent\":" + String(simulatedBatteryPercent) + ",";
  jsonPayload += "\"firmware_version\":\"" + String(FIRMWARE_VERSION) + "\",";
  
  // Events object
  jsonPayload += "\"events\":{";
  if (sosTriggered) {
    jsonPayload += "\"sos\":true,\"button_pressed\":true";
  }
  jsonPayload += "},";

  // Scan array
  jsonPayload += "\"scan\":[";
  for (int i = 0; i < n; ++i) {
    jsonPayload += "{";
    jsonPayload += "\"bssid\":\"" + WiFi.BSSIDstr(i) + "\",";
    jsonPayload += "\"rssi\":" + String(WiFi.RSSI(i)) + ",";
    jsonPayload += "\"channel\":" + String(WiFi.channel(i));
    jsonPayload += "}";
    if (i < n - 1) {
      jsonPayload += ",";
    }
  }
  jsonPayload += "]}";

  // 3. Publish telemetry to HiveMQ Cloud
  Serial.printf("[Cloud MQTT] Publishing %d bytes to topic '%s'...\n", jsonPayload.length(), TOPIC_TELEMETRY);
  bool published = mqttClient.publish(TOPIC_TELEMETRY, jsonPayload.c_str());

  if (published) {
    Serial.println("[Cloud MQTT] >> Telemetry successfully published to HiveMQ Cloud!");
  } else {
    Serial.println("[Cloud MQTT] !! Failed to publish telemetry. Checking connection...");
  }

  // 4. Wait for next tracking cycle
  delay(TRACKING_INTERVAL_MS);
}
