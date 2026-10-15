// ==========================================
// CHILDTRACK MASTER (SCANNER) FIRMWARE
// ==========================================
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// --- Hardware Pins ---
#define LED_POWER_PIN 25 // Red LED
#define LED_DATA_PIN 26  // Green LED

// --- Wi-Fi Configuration ---
const char* WIFI_SSID = "MITAOE";
const char* WIFI_PASSWORD = "MitAOE#2";

// --- HiveMQ Cloud Configuration ---
const char* MQTT_BROKER = "bba750cd4da045959dd983b09d38b17f.s1.eu.hivemq.cloud"; 
const int MQTT_PORT = 8883;
const char* MQTT_USERNAME = "inhousechildtracker";
const char* MQTT_PASSWORD = "childtracker@123";

// Ensure this topic matches the MQTT_TOPIC_TELEMETRY in your backend .env or mqtt_service
const char* MQTT_TOPIC = "childtrack/telemetry/scans"; 
const int SCAN_INTERVAL_MS = 5000; 

WiFiClientSecure espClient;
PubSubClient mqtt(espClient);
String scannerMac;
unsigned long lastScanTime = 0;

void setup() {
  Serial.begin(115200);

  // Initialize LEDs
  pinMode(LED_POWER_PIN, OUTPUT);
  pinMode(LED_DATA_PIN, OUTPUT);
  
  // Turn on Power LED immediately (Red)
  digitalWrite(LED_POWER_PIN, HIGH);
  digitalWrite(LED_DATA_PIN, LOW);

  WiFi.mode(WIFI_STA);
  
  // HiveMQ Cloud requires TLS/SSL connection on port 8883. 
  // For testing purposes, we skip certificate validation.
  espClient.setInsecure(); 
  
  connectWiFi();
  
  // Grab MAC after Wi-Fi connects to avoid 00:00:00 bug
  scannerMac = WiFi.macAddress();
  Serial.println("ChildTrack Master Scanner Booted.");
  Serial.println("Scanner MAC: " + scannerMac);
  
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqtt.connected()) connectMQTT();
  
  mqtt.loop();
  
  if (millis() - lastScanTime > SCAN_INTERVAL_MS) {
    lastScanTime = millis();
    performScanAndPublish();
  }
}

void connectWiFi() {
  Serial.print("Connecting to Wi-Fi...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi Connected!");
}

void connectMQTT() {
  while (!mqtt.connected()) {
    Serial.print("Connecting to HiveMQ Cloud...");
    
    // Create a unique client ID based on MAC
    String clientId = "CT-Scanner-" + scannerMac;
    
    // Connect using Username and Password
    if (mqtt.connect(clientId.c_str(), MQTT_USERNAME, MQTT_PASSWORD)) {
      Serial.println("Connected!");
    } else {
      Serial.print("Failed, rc=");
      Serial.print(mqtt.state());
      Serial.println(" retrying in 5s");
      delay(5000);
    }
  }
}

void performScanAndPublish() {
  Serial.println("Scanning for Tags...");
  int networkCount = WiFi.scanNetworks(false, false, false, 100);
  
  if (networkCount == 0) return;
  
  StaticJsonDocument<1024> doc;
  doc["scanner_mac"] = scannerMac;
  doc["timestamp"] = "TODO";
  JsonArray tags = doc.createNestedArray("tags");
  int tagsFound = 0;
  
  for (int i = 0; i < networkCount; ++i) {
    String ssid = WiFi.SSID(i);
    String bssid = WiFi.BSSIDstr(i);
    
    if (ssid.startsWith("CT-TAG-") || ssid.startsWith("SOS-TAG-")) {
      JsonObject tag = tags.createNestedObject();
      tag["mac"] = bssid;
      tag["rssi"] = WiFi.RSSI(i);
      tag["sos"] = ssid.startsWith("SOS-TAG-");
      tag["battery"] = 100; 
      
      if (tag["sos"]) Serial.println("! SOS DETECTED FROM " + bssid + " !");
      tagsFound++;
    }
  }
  
  if (tagsFound > 0) {
    char payload[1024];
    serializeJson(doc, payload);
    Serial.println("Publishing: " + String(payload));
    if (mqtt.publish(MQTT_TOPIC, payload)) {
       // Blink Green LED when we successfully receive tags AND publish them
       digitalWrite(LED_DATA_PIN, HIGH);
       delay(200);
       digitalWrite(LED_DATA_PIN, LOW);
    }
  } else {
    Serial.println("No Tags in range.");
  }
  WiFi.scanDelete(); 
}
