// ==========================================
// CHILDTRACK SLAVE (WEARABLE TAG) FIRMWARE
// ==========================================
#include <WiFi.h>

const char* BASE_SSID = "CT-TAG-"; 
const char* SOS_SSID = "SOS-TAG-"; 

// Pin for the SOS trigger. Touch this pin to Ground (GND) to trigger an SOS.
const int SOS_PIN = 15; 

bool sos_active = false;
unsigned long sos_start_time = 0;
const unsigned long SOS_DURATION_MS = 30000; // Broadcast SOS for 30 seconds

String macAddress;

void setup() {
  Serial.begin(115200);
  pinMode(SOS_PIN, INPUT_PULLUP);
  
  // 1. Temporarily boot into Station mode to reliably grab the MAC
  WiFi.mode(WIFI_STA);
  delay(100);
  macAddress = WiFi.macAddress();
  
  // 2. Switch back to Access Point mode for our beacon
  WiFi.mode(WIFI_AP);
  
  Serial.println("ChildTrack Wearable Tag Booted.");
  Serial.println("MAC Address: " + macAddress);
  
  updateBeacon(BASE_SSID);
}

void loop() {
  // If GPIO 15 is connected to GND, trigger SOS!
  if (digitalRead(SOS_PIN) == LOW) {
    if (!sos_active) {
      Serial.println("SOS TRIGGERED! Changing broadcast to SOS...");
      sos_active = true;
      sos_start_time = millis();
      updateBeacon(SOS_SSID);
    }
    delay(200); 
  }
  
  // Reset SOS after 30 seconds
  if (sos_active && (millis() - sos_start_time > SOS_DURATION_MS)) {
    Serial.println("SOS Duration expired. Returning to normal beacon.");
    sos_active = false;
    updateBeacon(BASE_SSID);
  }
  delay(10);
}

void updateBeacon(const char* prefix) {
  String ssid = String(prefix) + macAddress.substring(macAddress.length() - 8);
  ssid.replace(":", "");
  
  WiFi.softAPdisconnect(true);
  delay(100);
  // MaxConnections = 0 ensures it's just a beacon
  WiFi.softAP(ssid.c_str(), "childtrack", 1, 0, 0); 
  Serial.println("Broadcasting as: " + ssid);
}
