/*
  HavenIQ ESP32 device controller  (Light / Fan / AC)

  The ESP32 only needs: WiFi + the MQTT broker + two topics. It does NOT talk to Flask.

    SUBSCRIBES  home/devices/commands   {"device": "light", "state": "ON"}
    PUBLISHES   home/devices/status     {"light":"ON","fan":"OFF","ac":"OFF"}   (retained)

  Libraries (Arduino IDE -> Library Manager):  PubSubClient (Nick O'Leary),  ArduinoJson (v7)
  Board: "ESP32 Dev Module" (esp32 board package by Espressif)

  !! This sketch has NOT been compiled or tested on hardware by the author of this document.
  !! Read esp32/README_ESP32.md (mains-voltage safety) before connecting any real appliance.
*/
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ===================== USER SETTINGS =====================
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// IP address of the PC that runs Mosquitto (NOT "localhost" - that would be the ESP32 itself).
const char* MQTT_HOST     = "192.168.1.10";
const uint16_t MQTT_PORT  = 1883;
const char* MQTT_USER     = "";            // leave "" if the broker allows anonymous clients
const char* MQTT_PASS     = "";
const char* MQTT_CLIENT_ID = "haveniq-esp32";

const char* TOPIC_COMMANDS = "home/devices/commands";
const char* TOPIC_STATUS   = "home/devices/status";

// Configurable output pins. These are PLACEHOLDERS: change them to the pins you wired.
// Avoid pins 6-11 (flash), 34-39 (input only) and the boot/strapping pins 0, 2, 5, 12, 15.
#define LIGHT_PIN 26
#define FAN_PIN   27
#define AC_PIN    25

// Most relay modules switch ON when the pin is LOW ("active low"). Set false if yours is active high.
#define RELAY_ACTIVE_LOW true

const unsigned long STATUS_HEARTBEAT_MS = 30000;   // re-publish the state every 30 s
// ==========================================================

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

bool lightOn = false, fanOn = false, acOn = false;   // boots with everything OFF
unsigned long lastStatusMs = 0, lastReconnectMs = 0;

void writeOutput(uint8_t pin, bool on) {
  digitalWrite(pin, (on ^ RELAY_ACTIVE_LOW) ? HIGH : LOW);
}

void publishStatus() {
  char buf[80];
  snprintf(buf, sizeof(buf), "{\"light\":\"%s\",\"fan\":\"%s\",\"ac\":\"%s\"}",
           lightOn ? "ON" : "OFF", fanOn ? "ON" : "OFF", acOn ? "ON" : "OFF");
  if (mqtt.publish(TOPIC_STATUS, buf, true)) {       // true = retained
    Serial.print("status -> "); Serial.println(buf);
  } else {
    Serial.println("status publish failed");
  }
  lastStatusMs = millis();
}

// Called for every message on home/devices/commands
void onMessage(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, length)) { Serial.println("ignored: malformed JSON"); return; }
  const char* device = doc["device"];
  const char* state  = doc["state"];
  if (!device || !state) { Serial.println("ignored: needs \"device\" and \"state\""); return; }

  bool on;
  if (strcasecmp(state, "ON") == 0) on = true;
  else if (strcasecmp(state, "OFF") == 0) on = false;
  else { Serial.println("ignored: state must be ON or OFF"); return; }

  if      (strcasecmp(device, "light") == 0) { lightOn = on; writeOutput(LIGHT_PIN, on); }
  else if (strcasecmp(device, "fan")   == 0) { fanOn   = on; writeOutput(FAN_PIN,   on); }
  else if (strcasecmp(device, "ac")    == 0) { acOn    = on; writeOutput(AC_PIN,    on); }
  else { Serial.println("ignored: unknown device"); return; }

  Serial.printf("command: %s -> %s\n", device, state);
  publishStatus();                                   // report the ACTUAL state back
}

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print("WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) { delay(300); Serial.print("."); }
  Serial.println(WiFi.status() == WL_CONNECTED ? " connected" : " failed (will retry)");
}

void connectMqtt() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  if (millis() - lastReconnectMs < 5000 && lastReconnectMs != 0) return;   // retry every 5 s
  lastReconnectMs = millis();
  Serial.print("MQTT...");
  bool ok = strlen(MQTT_USER) ? mqtt.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS) : mqtt.connect(MQTT_CLIENT_ID);
  if (ok) {
    Serial.println(" connected");
    mqtt.subscribe(TOPIC_COMMANDS, 1);
    publishStatus();                                 // tell the dashboard our real state
  } else {
    Serial.printf(" failed, rc=%d\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LIGHT_PIN, OUTPUT); pinMode(FAN_PIN, OUTPUT); pinMode(AC_PIN, OUTPUT);
  writeOutput(LIGHT_PIN, false); writeOutput(FAN_PIN, false); writeOutput(AC_PIN, false);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.setCallback(onMessage);
  connectWifi();
}

void loop() {
  connectWifi();
  connectMqtt();
  if (mqtt.connected()) {
    mqtt.loop();
    if (millis() - lastStatusMs > STATUS_HEARTBEAT_MS) publishStatus();
  }
}
