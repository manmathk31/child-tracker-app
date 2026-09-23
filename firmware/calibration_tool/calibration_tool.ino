/*
 * ChildTrack - ESP32 Physical Zone Calibration Tool
 * 
 * Instructions:
 * 1. Set your Wi-Fi SSID and Password.
 * 2. Set your laptop's local IP address (find using 'ipconfig' in PowerShell).
 * 3. Set the survey UUID from your browser URL:
 *    http://localhost:8000/fingerprints/<SURVEY_UUID>/calibrate
 * 4. Flash to your ESP32 board and place it in the room you are calibrating.
 * 5. Open Serial Monitor at 115200 baud to watch live calibration transmissions.
 */

#include <WiFi.h>
#include <HTTPClient.h>

// ==============================================================================
// Configuration Settings
// ==============================================================================
const char* WIFI_SSID     = "YOUR_WIFI_OR_HOTSPOT_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Replace with your laptop's local IPv4 address (e.g., 192.168.1.15 or 192.168.43.100)
const char* SERVER_IP     = "192.168.1.15";
const int   SERVER_PORT   = 8000;

// Paste the Survey UUID from the ChildTrack browser URL here:
const char* SURVEY_ID     = "PASTE_SURVEY_UUID_HERE";

// Time between calibration scan bursts (milliseconds)
const unsigned long SCAN_INTERVAL_MS = 2500;

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n==================================================");
  Serial.println("   ChildTrack ESP32 Physical Zone Calibration Tool");
  Serial.println("==================================================");

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
  Serial.printf("[Target] Survey UUID     : %s\n\n", SURVEY_ID);
}

void loop() {
  Serial.println("[Scanner] Scanning physical radio frequencies...");
  int n = WiFi.scanNetworks(false, true); // (async=false, show_hidden=true)

  if (n <= 0) {
    Serial.println("[Scanner] No Wi-Fi access points detected in this area.");
    delay(SCAN_INTERVAL_MS);
    return;
  }

  Serial.printf("[Scanner] Detected %d access points. Packaging JSON...\n", n);

  // Build JSON payload conforming to ChildTrack Calibration Protocol
  String jsonPayload = "{\"scan\":[";
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

  // Transmit sample burst via HTTP POST to ChildTrack
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String endpoint = "http://" + String(SERVER_IP) + ":" + String(SERVER_PORT) + 
                      "/api/v1/fingerprints/" + String(SURVEY_ID) + "/samples";

    http.begin(endpoint);
    http.addHeader("Content-Type", "application/json");

    int httpCode = http.POST(jsonPayload);
    if (httpCode == 200 || httpCode == 201) {
      String response = http.getString();
      Serial.printf("[Server OK %d] Sample burst recorded! Check your browser!\n", httpCode);
    } else if (httpCode > 0) {
      Serial.printf("[Server Error %d] Response: %s\n", httpCode, http.getString().c_str());
    } else {
      Serial.printf("[Network Error] Connection failed: %s\n", http.errorToString(httpCode).c_str());
      Serial.println("  -> Check that your laptop IP is correct and ChildTrack server is running.");
    }
    http.end();
  } else {
    Serial.println("[Wi-Fi] Disconnected! Reconnecting...");
    WiFi.reconnect();
  }

  // Delay before next physical scan
  delay(SCAN_INTERVAL_MS);
}
