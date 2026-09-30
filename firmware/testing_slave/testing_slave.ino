/*
 * ChildTrack - Testing Portal: Slave ESP (Child Wearable Beacon Tag)
 * 
 * Instructions:
 * 1. Flash this code onto ESP #1 (Slave ESP).
 * 2. Power it from any USB port or power bank.
 * 3. It broadcasts a private beacon "CT-SLAVE-TAG" continuously.
 * 4. Zero router / Wi-Fi setup needed on this board! Extremely power efficient.
 */

#include <WiFi.h>

#define BEACON_SSID  "CT-SLAVE-TAG"
#define BEACON_PASS  "ChildTrack123"

// Optional onboard LED pin (GPIO 2 is the blue LED on most ESP32 boards)
#define LED_PIN 2

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);

  Serial.println("\n========================================================");
  Serial.println("  ChildTrack Tether Lab - Slave ESP (Proximity Beacon)  ");
  Serial.println("========================================================");

  // Broadcast private beacon hotspot (Channel 1, broadcast SSID, max 1 connection)
  WiFi.mode(WIFI_AP);
  WiFi.softAP(BEACON_SSID, BEACON_PASS, 1, 0, 1);

  Serial.printf("[Beacon] Beacon initialized: %s\n", BEACON_SSID);
  Serial.println("[Beacon] >> Broadcasting proximity signals continuously...");
}

int cycleCount = 0;

void loop() {
  // Gentle heartbeat pulse on onboard LED every 1 second
  digitalWrite(LED_PIN, HIGH);
  delay(100);
  digitalWrite(LED_PIN, LOW);
  delay(900);

  cycleCount++;
  if (cycleCount % 5 == 0) {
    Serial.printf("[Slave Tag] Broadcasting '%s' (Heartbeat #%d)\n", BEACON_SSID, cycleCount);
  }
}
