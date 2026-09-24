/*
 * ChildTrack - ESP32 Physical Zone Calibration Tool (Cloud MQTT Edition)
 * 
 * Instructions:
 * 1. Open Arduino IDE -> Sketch -> Include Library -> Manage Libraries...
 *    Make sure "PubSubClient" (by Nick O'Leary) is installed.
 * 2. Set your Wi-Fi SSID and Password.
 * 3. Set your HiveMQ Cloud password for user "inhousechildtracker".
 * 4. Paste the Survey UUID from your browser URL:
 *    Example: http://localhost:8000/fingerprints/02eea9ca-97d1-4f3a-a621-620cc4158f48/calibrate
 *    -> SURVEY_ID = "02eea9ca-97d1-4f3a-a621-620cc4158f48"
 * 5. Flash this code to your ESP32 and place the board in the room you are calibrating!
 * 6. Watch the Serial Monitor at 115200 baud and refresh your browser calibration page!
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

// ==============================================================================
// 1. Wi-Fi Configuration (Any Wi-Fi or Mobile Hotspot)
// ==============================================================================
const char* WIFI_SSID        = "YOUR_WIFI_OR_HOTSPOT_NAME";
const char* WIFI_PASSWORD    = "YOUR_WIFI_PASSWORD";

// ==============================================================================
// 2. HiveMQ Cloud MQTT Configuration
// ==============================================================================
const char* MQTT_BROKER      = "bba750cd4da045959dd983b09d38b17f.s1.eu.hivemq.cloud";
const int   MQTT_PORT        = 8883; // Secure TLS
const char* MQTT_USER        = "inhousechildtracker";
const char* MQTT_PASSWORD    = "YOUR_HIVEMQ_PASSWORD_HERE"; // Enter your HiveMQ password!

// ==============================================================================
// 3. Survey Calibration Target
// ==============================================================================
// Copy the Survey UUID from your browser URL:
// http://localhost:8000/fingerprints/<SURVEY_UUID>/calibrate
const char* SURVEY_ID        = "02eea9ca-97d1-4f3a-a621-620cc4158f48";

// Calibration burst interval (milliseconds)
const unsigned long SCAN_INTERVAL_MS = 2500;

// ==============================================================================
// Secure Client & MQTT Instance
// ==============================================================================
WiFiClientSecure espClient;
PubSubClient     mqttClient(espClient);

int burstCount = 0;

void onCalibrationAck(char* topic, byte* payload, unsigned int length) {
  String response = "";
  for (unsigned int i = 0; i < length; i++) {
    response += (char)payload[i];
  }
  Serial.printf("\n[Server Cloud ACK] Received: %s\n", response.c_str());
  Serial.println("  -> Sample recorded in ChildTrack! Check your browser page!");
}

void ensureMqttConnected() {
  while (!mqttClient.connected()) {
    Serial.print("[Cloud MQTT] Connecting to HiveMQ Cloud broker...");
    String clientId = "ChildTrackCalibrator-" + String(random(0xffff), HEX);
    
    if (mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD)) {
      Serial.println(" CONNECTED!");
      
      // Subscribe to personal calibration acknowledgement topic
      String ackTopic = "childtrack/ack/calibration/" + String(SURVEY_ID);
      mqttClient.subscribe(ackTopic.c_str());
      Serial.printf("[Cloud MQTT] Subscribed to ACK topic: %s\n", ackTopic.c_str());
    } else {
      Serial.printf(" FAILED (rc=%d). Retrying in 3 seconds...\n", mqttClient.state());
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n========================================================");
  Serial.println("  ChildTrack ESP32 Fingerprint Calibrator - Cloud Edition");
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
  Serial.printf("[Target] Survey UUID     : %s\n", SURVEY_ID);

  // 2. Configure Secure TLS MQTT
  espClient.setInsecure();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(onCalibrationAck);
  mqttClient.setBufferSize(2048);

  ensureMqttConnected();
}

void loop() {
  if (!mqttClient.connected()) {
    ensureMqttConnected();
  }
  mqttClient.loop();

  // 1. Scan nearby Wi-Fi APs
  Serial.println("\n[Scanner] Scanning physical radio frequencies...");
  int n = WiFi.scanNetworks(false, true);

  if (n <= 0) {
    Serial.println("[Scanner] No Wi-Fi access points detected in this area.");
    delay(SCAN_INTERVAL_MS);
    return;
  }

  burstCount++;
  Serial.printf("[Scanner] Burst #%d: Detected %d APs. Packaging JSON...\n", burstCount, n);

  // 2. Build JSON matching ChildTrack CalibrationBatchIn schema
  String jsonPayload = "{\"device_id\":\"ESP32-CALIBRATOR\",\"scan\":[";
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

  // 3. Publish to cloud topic
  String topic = "childtrack/calibration/" + String(SURVEY_ID);
  Serial.printf("[Cloud MQTT] Publishing %d bytes to '%s'...\n", jsonPayload.length(), topic.c_str());
  bool published = mqttClient.publish(topic.c_str(), jsonPayload.c_str());

  if (published) {
    Serial.println("[Cloud MQTT] >> Calibration burst sent to HiveMQ Cloud!");
  } else {
    Serial.println("[Cloud MQTT] !! Failed to publish. Check connection/buffer size.");
  }

  // 4. Delay before next scan burst
  delay(SCAN_INTERVAL_MS);
}
