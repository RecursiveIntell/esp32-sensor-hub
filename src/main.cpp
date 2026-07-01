#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <DHT.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include "config.h"
#include "sensor_policy_contract.h"

#ifndef WIFI_PASSWORD_PRIMARY
#define WIFI_PASSWORD_PRIMARY ""
#endif
#ifndef WIFI_PASSWORD_SECONDARY
#define WIFI_PASSWORD_SECONDARY ""
#endif
#ifndef AI_STREAM_URL
#define AI_STREAM_URL AI_INFER_URL
#endif
#ifndef AI_INTERVAL_MS
#define AI_INTERVAL_MS 300000
#endif
#ifndef AI_STREAM_MAX_MS
#define AI_STREAM_MAX_MS 120000
#endif
#ifndef AI_PROMPT
#define AI_PROMPT "Do not just repeat the sensor numbers. Interpret the room comfort from the temp/humidity, say if it feels normal/humid/dry/hot/cool, and give one practical action if useful. One short OLED-friendly sentence."
#endif
#ifndef OLLAMA_MODEL
#define OLLAMA_MODEL "gemma4:12b"
#endif
#ifndef LOCAL_LANGUAGE_URL
#define LOCAL_LANGUAGE_URL ""
#endif

WebServer server(80);
DHT dht(DHT_PIN, DHT_TYPE);
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);

struct SensorState {
  float temperature_c = NAN;
  float temperature_f = NAN;
  float humidity_pct = NAN;
  float heat_index_c = NAN;
  float heat_index_f = NAN;
  bool valid = false;
  bool oled_ok = false;
  bool ai_active = false;
  unsigned long last_read_ms = 0;
  unsigned long last_post_ms = 0;
  unsigned long last_ai_ms = 0;
  unsigned long last_local_language_ms = 0;
  int last_post_code = 0;
  int last_ai_code = 0;
  int last_local_language_code = 0;
  String last_post_result = "never";
  String last_ai_result = "never";
  String last_local_language_prompt = "never";
  String last_local_language_output = "never";
  String active_wifi_password_label = "none";
};

SensorState state;
uint64_t proof_event_id = 1;

String ipString() {
  if (WiFi.status() != WL_CONNECTED) return "0.0.0.0";
  return WiFi.localIP().toString();
}

String millisAge(unsigned long then_ms) {
  if (then_ms == 0) return "never";
  unsigned long sec = (millis() - then_ms) / 1000;
  if (sec < 60) return String(sec) + "s";
  return String(sec / 60) + "m" + String(sec % 60) + "s";
}

void oledLine(const String &s) {
  display.println(s.substring(0, 21));
}

void drawStatus(const char *line1 = nullptr) {
  if (!state.oled_ok) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  oledLine(line1 ? String(line1) : String(DEVICE_ID));
  display.print("WiFi:");
  display.print(WiFi.status() == WL_CONNECTED ? "ok " : "down ");
  display.println(ipString());
  display.print("RSSI:");
  display.print(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0);
  display.print(" heap:");
  display.println(ESP.getFreeHeap());
  if (state.valid) {
    display.print("T:");
    display.print(state.temperature_f, 1);
    display.print("F H:");
    display.print(state.humidity_pct, 1);
    display.println("%");
    display.print("HI:");
    display.print(state.heat_index_f, 1);
    display.print("F age:");
    display.println(millisAge(state.last_read_ms));
  } else {
    display.println("Sensor: read failed");
    display.print("age:");
    display.println(millisAge(state.last_read_ms));
  }
  display.print("POST:");
  display.print(state.last_post_code);
  display.print(" S3:");
  display.println(state.last_local_language_code);
  oledLine("S3: " + state.last_local_language_output);
  display.display();
}

void drawWrappedText(const String &title, const String &text) {
  if (!state.oled_ok) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  oledLine(title);

  const int maxCharsPerLine = 21;
  const int maxLines = 7;
  int len = text.length();
  int start = 0;
  if (len > maxCharsPerLine * maxLines) {
    start = len - (maxCharsPerLine * maxLines);
    while (start < len && text[start] != ' ' && text[start] != '\n') start++;
    if (start < len) start++;
  }

  int line = 0;
  int pos = start;
  while (line < maxLines && pos < len) {
    String out = "";
    while (pos < len && out.length() < maxCharsPerLine) {
      char c = text[pos++];
      if (c == '\r') continue;
      if (c == '\n') break;
      out += c;
    }
    oledLine(out);
    line++;
  }
  display.display();
}

void scanWifiNetworks() {
  Serial.println("Scanning visible 2.4GHz WiFi networks...");
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(false, false);
  delay(300);
  int n = WiFi.scanNetworks(/*async=*/false, /*hidden=*/true);
  if (n <= 0) {
    Serial.printf("WiFi scan found %d networks\n", n);
    return;
  }
  bool found = false;
  for (int i = 0; i < n; i++) {
    String ssid = WiFi.SSID(i);
    int32_t rssi = WiFi.RSSI(i);
    int32_t channel = WiFi.channel(i);
    wifi_auth_mode_t enc = WiFi.encryptionType(i);
    Serial.printf("  AP[%02d] ssid='%s' rssi=%d channel=%d enc=%d%s\n",
                  i, ssid.c_str(), rssi, channel, enc,
                  ssid == WIFI_SSID ? "  <-- target" : "");
    if (ssid == WIFI_SSID) found = true;
  }
  Serial.printf("Target SSID '%s' visible: %s\n", WIFI_SSID, found ? "yes" : "no");
  WiFi.scanDelete();
}

bool tryWifiPassword(const char *password, const char *label, uint32_t timeout_ms) {
  if (password == nullptr || strlen(password) == 0 || strcmp(password, "CHANGE_ME") == 0) return false;
  Serial.printf("Connecting to %s using %s password...\n", WIFI_SSID, label);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.disconnect(false, false);
  delay(300);
  wl_status_t begin_status = WiFi.begin(WIFI_SSID, password);
  if (begin_status == WL_CONNECT_FAILED) {
    Serial.println("WiFi.begin returned WL_CONNECT_FAILED");
    return false;
  }

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < timeout_ms) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    state.active_wifi_password_label = label;
    Serial.printf("WiFi connected. IP=%s RSSI=%d dBm\n", ipString().c_str(), WiFi.RSSI());
    return true;
  }
  Serial.printf("WiFi failed with %s password. status=%d\n", label, WiFi.status());
  return false;
}

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  drawStatus("WiFi connect...");
  if (tryWifiPassword(WIFI_PASSWORD_PRIMARY, "primary", 12000)) return;
  if (tryWifiPassword(WIFI_PASSWORD_SECONDARY, "secondary", 12000)) return;
  Serial.println("WiFi failed with both configured passwords.");
  drawStatus("WiFi failed");
}

void readSensors() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    state.valid = false;
    state.last_read_ms = millis();
    Serial.println("DHT read failed");
    return;
  }

  state.humidity_pct = h;
  state.temperature_c = t;
  state.temperature_f = (t * 9.0f / 5.0f) + 32.0f;
  state.heat_index_c = dht.computeHeatIndex(t, h, false);
  state.heat_index_f = (state.heat_index_c * 9.0f / 5.0f) + 32.0f;
  state.valid = true;
  state.last_read_ms = millis();
  Serial.printf("Sensor: %.2f F / %.2f C %.2f %% heat-index %.2f F\n", state.temperature_f, t, h, state.heat_index_f);
}

float sentinelConfidence() {
  if (!state.valid) return 0.0f;
  float confidence = 0.95f;
  if (state.humidity_pct > 60.0f || state.humidity_pct < 30.0f) confidence -= 0.18f;
  if (state.temperature_f > 78.0f || state.temperature_f < 65.0f) confidence -= 0.18f;
  if (confidence < 0.05f) confidence = 0.05f;
  if (confidence > 0.99f) confidence = 0.99f;
  return confidence;
}


String canonicalLocalLanguagePrompt() {
  if (!state.valid) return RI_PROMPT_MISSING_SENSOR;
  if (state.last_read_ms > 0 && millis() - state.last_read_ms > RI_POLICY_STALE_AFTER_MS) return RI_PROMPT_STALE_DATA;
  bool hot = state.temperature_f >= RI_POLICY_HOT_F;
  bool cold = state.temperature_f <= RI_POLICY_COLD_F;
  bool humid = state.humidity_pct >= RI_POLICY_HUMID_PCT;
  bool dry = state.humidity_pct <= RI_POLICY_DRY_PCT;
  if (hot && humid) return RI_PROMPT_HIGH_HEAT_HUMIDITY;
  if (hot) return RI_PROMPT_HOT_ROOM;
  if (humid) return RI_PROMPT_HUMID_ROOM;
  if (cold || dry) return RI_PROMPT_SAFE_ACTION;
  return RI_PROMPT_NORMAL_ROOM;
}

String routeReason(const String &trigger = "schedule_tick") {
  if (!state.valid) return "sensor_missing";
  if (state.last_read_ms > 0 && millis() - state.last_read_ms > RI_POLICY_STALE_AFTER_MS) return "stale_reading";
  if (trigger == "operator_request") return "operator_request";
  bool hot = state.temperature_f >= RI_POLICY_HOT_F;
  bool cold = state.temperature_f <= RI_POLICY_COLD_F;
  bool humid = state.humidity_pct >= RI_POLICY_HUMID_PCT;
  bool dry = state.humidity_pct <= RI_POLICY_DRY_PCT;
  if (hot && humid) return "temperature_and_humidity_out_of_range";
  if (cold || dry) return "unsupported_cold_or_dry";
  if (humid) return "humidity_out_of_range";
  if (hot) return "temperature_out_of_range";
  if (sentinelConfidence() < 0.75f) return "low_confidence";
  if (trigger == "anomaly_match") return "anomaly_match";
  if (trigger == "schedule_tick") return "schedule_tick";
  return "local_confident";
}

String routeDecision(const String &reason) {
  return reason == "local_confident" ? "local_only" : "forward_to_ai";
}

String sensorJson(bool include_ai_envelope = false, const String &request_body = "") {
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["uptime_ms"] = millis();
  doc["free_heap"] = ESP.getFreeHeap();
  doc["chip_model"] = ESP.getChipModel();
  doc["wifi_status"] = WiFi.status() == WL_CONNECTED ? "connected" : "disconnected";
  doc["wifi_rssi"] = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0;
  doc["ip"] = ipString();
  doc["wifi_password_slot"] = state.active_wifi_password_label;
  doc["status"] = state.valid ? "ok" : "sensor_read_failed";
  if (state.valid) {
    doc["temperature_c"] = state.temperature_c;
    doc["temperature_f"] = state.temperature_f;
    doc["humidity_pct"] = state.humidity_pct;
    doc["heat_index_c"] = state.heat_index_c;
    doc["heat_index_f"] = state.heat_index_f;
  } else {
    doc["temperature_c"] = nullptr;
    doc["temperature_f"] = nullptr;
    doc["humidity_pct"] = nullptr;
    doc["heat_index_c"] = nullptr;
    doc["heat_index_f"] = nullptr;
  }

  JsonObject sensors = doc["sensors"].to<JsonObject>();
  JsonObject dht22 = sensors["dht"].to<JsonObject>();
  dht22["type"] = "DHT";
  dht22["pin"] = DHT_PIN;
  dht22["valid"] = state.valid;
  dht22["temperature_c"] = state.valid ? state.temperature_c : NAN;
  dht22["temperature_f"] = state.valid ? state.temperature_f : NAN;
  dht22["humidity_pct"] = state.valid ? state.humidity_pct : NAN;
  dht22["heat_index_c"] = state.valid ? state.heat_index_c : NAN;
  dht22["heat_index_f"] = state.valid ? state.heat_index_f : NAN;
  dht22["last_read_ms"] = state.last_read_ms;

  JsonObject oled = sensors["oled"].to<JsonObject>();
  oled["type"] = "SSD1306";
  oled["width"] = OLED_WIDTH;
  oled["height"] = OLED_HEIGHT;
  oled["addr"] = OLED_ADDR;
  oled["ok"] = state.oled_ok;

  doc["last_read_ms"] = state.last_read_ms;
  doc["last_post_code"] = state.last_post_code;
  doc["last_post_result"] = state.last_post_result;
  doc["last_ai_ms"] = state.last_ai_ms;
  doc["last_ai_code"] = state.last_ai_code;
  doc["last_ai_result"] = state.last_ai_result;
  doc["local_language_url"] = LOCAL_LANGUAGE_URL;
  doc["last_local_language_ms"] = state.last_local_language_ms;
  doc["last_local_language_code"] = state.last_local_language_code;
  doc["last_local_language_prompt"] = state.last_local_language_prompt;
  doc["last_local_language_output"] = state.last_local_language_output;

  String trigger = include_ai_envelope ? "operator_request" : "schedule_tick";
  String reason = routeReason(trigger);
  JsonObject proof = doc["proof"].to<JsonObject>();
  proof["schema"] = "ri_esp_proof_receipt_v1";
  proof["event_id"] = proof_event_id++;
  proof["device_id"] = DEVICE_ID;
  proof["timestamp_ms"] = millis();
  proof["decision"] = routeDecision(reason);
  proof["reason"] = reason;
  proof["route_reason"] = reason;
  proof["sentinel_confidence"] = sentinelConfidence();
  proof["ai_route"] = OLLAMA_MODEL;
  proof["local_language_model"] = RI_LOCAL_LANGUAGE_MODEL;
  proof["local_language_prompt"] = canonicalLocalLanguagePrompt();
  proof["local_language_contract"] = RI_SENSOR_POLICY_CONTRACT_SCHEMA;
  JsonObject proof_sensor = proof["sensor"].to<JsonObject>();
  proof_sensor["temperature_c"] = state.valid ? state.temperature_c : NAN;
  proof_sensor["humidity_pct"] = state.valid ? state.humidity_pct : NAN;
  proof_sensor["heat_index_c"] = state.valid ? state.heat_index_c : NAN;

  if (include_ai_envelope) {
    JsonObject ai = doc["ai_request"].to<JsonObject>();
    ai["raw_body"] = request_body.length() ? request_body : String("{\"prompt\":\"") + AI_PROMPT + "\"}";
    ai["note"] = "ESP32 forwards sensor context; GTX server performs inference";
    ai["stream_target"] = "oled";
  }

  String out;
  serializeJson(doc, out);
  return out;
}

String promptFromRequestJson(const String &request_body) {
  if (request_body.length() == 0) return String(AI_PROMPT);
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, request_body);
  if (err) return request_body;
  const char *prompt = doc["prompt"];
  if (prompt) return String(prompt);
  const char *question = doc["question"];
  if (question) return String(question);
  const char *message = doc["message"];
  if (message) return String(message);
  return String(AI_PROMPT);
}

String ollamaChatJson(bool stream, const String &request_body) {
  JsonDocument doc;
  doc["model"] = OLLAMA_MODEL;
  doc["stream"] = stream;
  doc["think"] = false;
  JsonObject options = doc["options"].to<JsonObject>();
  options["temperature"] = 0.2;
  options["top_p"] = 0.9;
  options["num_predict"] = stream ? 96 : 160;

  JsonArray messages = doc["messages"].to<JsonArray>();
  JsonObject system = messages.add<JsonObject>();
  system["role"] = "system";
  system["content"] = "You are the local Ollama AI tier for an ESP32 room sensor. Use only the provided sensor JSON as evidence. Do not merely restate temperature and humidity. Interpret comfort/risk and give one practical action if useful. Keep the final answer under 90 characters for a 128x64 OLED. No markdown.";

  String user_content = "Sensor context JSON:\n" + sensorJson(false) +
                        "\n\nComfort guidance: around 68-76F and 30-60% humidity is usually comfortable. Above 60% humidity can feel muggy; below 30% can feel dry.\n\nOperator request:\n" +
                        promptFromRequestJson(request_body);
  JsonObject user = messages.add<JsonObject>();
  user["role"] = "user";
  user["content"] = user_content;

  String out;
  serializeJson(doc, out);
  return out;
}

String extractResponseText(const String &json) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) return json.substring(0, 160);
  const char *response = doc["response"];
  if (response) return String(response);
  const char *content = doc["message"]["content"];
  if (content) return String(content);
  const char *error = doc["error"];
  if (error) return String("ERR: ") + error;
  return json.substring(0, 160);
}

String extractOllamaStreamContent(const String &line) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) return "";
  const char *content = doc["message"]["content"];
  return content ? String(content) : String("");
}

void postSensors() {
  if (WiFi.status() != WL_CONNECTED) {
    state.last_post_code = -1;
    state.last_post_result = "wifi_down";
    return;
  }

  HTTPClient http;
  String payload = sensorJson(false);
  http.begin(HUB_POST_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);
  int code = http.POST(payload);
  String body = http.getString();
  http.end();

  state.last_post_code = code;
  state.last_post_result = body.substring(0, 80);
  Serial.printf("POST %s -> %d %s\n", HUB_POST_URL, code, state.last_post_result.c_str());
}


void postLocalLanguage() {
  if (strlen(LOCAL_LANGUAGE_URL) == 0) return;
  if (WiFi.status() != WL_CONNECTED) {
    state.last_local_language_code = -1;
    state.last_local_language_output = "wifi_down";
    return;
  }

  HTTPClient http;
  String payload = sensorJson(false);
  http.begin(LOCAL_LANGUAGE_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(30000);
  int code = http.POST(payload);
  String body = http.getString();
  http.end();

  state.last_local_language_ms = millis();
  state.last_local_language_code = code;
  state.last_local_language_prompt = canonicalLocalLanguagePrompt();

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, body);
  if (!err) {
    const char *output = doc["local_language"]["output"];
    if (!output) output = doc["output"];
    const char *prompt = doc["local_language"]["prompt"];
    if (prompt) state.last_local_language_prompt = String(prompt);
    state.last_local_language_output = output ? String(output).substring(0, 80) : body.substring(0, 80);
  } else {
    state.last_local_language_output = body.substring(0, 80);
  }

  Serial.printf("LOCAL_LANGUAGE %s -> %d prompt='%s' output='%s'\n",
                LOCAL_LANGUAGE_URL, code, state.last_local_language_prompt.c_str(),
                state.last_local_language_output.c_str());
  if (code > 0 && code < 400) {
    drawWrappedText("S3 local language", state.last_local_language_output);
  }
}

void streamAiToOled(const String &promptJson) {
  if (WiFi.status() != WL_CONNECTED) {
    state.last_ai_code = -1;
    state.last_ai_result = "wifi_down";
    drawStatus("AI skipped WiFi down");
    return;
  }

  state.ai_active = true;
  state.last_ai_ms = millis();
  drawWrappedText("AI -> Gemma4", "Sending sensor context to GTX 1070...");

  HTTPClient http;
  String payload = ollamaChatJson(true, promptJson);
  http.begin(AI_STREAM_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(15000);

  int code = http.POST((uint8_t *)payload.c_str(), payload.length());
  state.last_ai_code = code;
  Serial.printf("AI stream POST %s -> %d\n", AI_STREAM_URL, code);

  if (code <= 0) {
    state.last_ai_result = String("http_error_") + code;
    http.end();
    state.ai_active = false;
    drawWrappedText("AI failed", state.last_ai_result);
    return;
  }

  WiFiClient *stream = http.getStreamPtr();
  String shown = "";
  String head = "";
  unsigned long start = millis();
  unsigned long last_byte = millis();
  unsigned long last_draw = 0;

  while (http.connected() && (millis() - start) < AI_STREAM_MAX_MS) {
    int avail = stream->available();
    if (avail > 0) {
      String line = stream->readStringUntil('\n');
      last_byte = millis();
      line.trim();
      if (line.length() == 0) continue;
      String content = extractOllamaStreamContent(line);
      if (content.length() == 0) continue;
      shown += content;
      if (head.length() < 160) head += content;
      if (shown.length() > 420) shown = shown.substring(shown.length() - 420);
      if (millis() - last_draw > 250) {
        drawWrappedText("Gemma4 streaming", shown);
        last_draw = millis();
      }
    } else {
      if ((millis() - last_byte) > 20000 && shown.length() > 0) break;
      server.handleClient();
      delay(10);
    }
  }

  if (shown.length() == 0) {
    String fallback = http.getString();
    shown = fallback.length() ? fallback : String("no response body");
    head = shown.substring(0, 160);
  }

  http.end();
  state.ai_active = false;
  state.last_ai_result = head.substring(0, 80);
  drawWrappedText(String("Gemma4 ") + code, shown);
  Serial.printf("AI stream done: %s\n", state.last_ai_result.c_str());
}

void periodicAiIfDue() {
  if (state.ai_active) return;
  if (AI_INTERVAL_MS == 0) return;
  unsigned long now = millis();
  if (state.last_ai_ms != 0 && now - state.last_ai_ms < AI_INTERVAL_MS) return;
  if (!state.valid) return;
  String prompt = String("{\"prompt\":\"") + AI_PROMPT + "\"}";
  streamAiToOled(prompt);
}

void handleStatus() {
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["uptime_ms"] = millis();
  doc["wifi_connected"] = WiFi.status() == WL_CONNECTED;
  doc["ip"] = ipString();
  doc["rssi"] = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0;
  doc["free_heap"] = ESP.getFreeHeap();
  doc["active_wifi_password_slot"] = state.active_wifi_password_label;
  doc["sensor_valid"] = state.valid;
  doc["oled_ok"] = state.oled_ok;
  doc["hub_post_url"] = HUB_POST_URL;
  doc["ai_infer_url"] = AI_INFER_URL;
  doc["ai_stream_url"] = AI_STREAM_URL;
  doc["ai_interval_ms"] = AI_INTERVAL_MS;
  doc["last_ai_code"] = state.last_ai_code;
  doc["last_ai_result"] = state.last_ai_result;
  doc["last_local_language_ms"] = state.last_local_language_ms;
  doc["last_local_language_code"] = state.last_local_language_code;
  doc["last_local_language_prompt"] = state.last_local_language_prompt;
  doc["last_local_language_output"] = state.last_local_language_output;
  String out;
  serializeJson(doc, out);
  server.send(200, "application/json", out);
}

void handleSensors() {
  server.send(200, "application/json", sensorJson(false));
}

void handleAiForward() {
  String body = server.hasArg("plain") ? server.arg("plain") : String("{\"prompt\":\"") + AI_PROMPT + "\"}";
  if (WiFi.status() != WL_CONNECTED) {
    server.send(503, "application/json", "{\"error\":\"wifi_down\"}");
    return;
  }

  HTTPClient http;
  String payload = ollamaChatJson(false, body);
  http.begin(AI_INFER_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(60000);
  int code = http.POST(payload);
  String response = http.getString();
  http.end();

  state.last_ai_ms = millis();
  state.last_ai_code = code;
  String text = extractResponseText(response);
  state.last_ai_result = text.substring(0, 80);
  drawWrappedText(String("AI HTTP ") + code, text);

  server.send(code > 0 ? code : 502, "application/json", response.length() ? response : "{\"error\":\"ai_forward_failed\"}");
}

void handleAiStreamNow() {
  String body = server.hasArg("plain") ? server.arg("plain") : String("{\"prompt\":\"") + AI_PROMPT + "\"}";
  streamAiToOled(body);
  JsonDocument doc;
  doc["ok"] = state.last_ai_code > 0 && state.last_ai_code < 400;
  doc["last_ai_code"] = state.last_ai_code;
  doc["last_ai_result"] = state.last_ai_result;
  doc["last_local_language_ms"] = state.last_local_language_ms;
  doc["last_local_language_code"] = state.last_local_language_code;
  doc["last_local_language_prompt"] = state.last_local_language_prompt;
  doc["last_local_language_output"] = state.last_local_language_output;
  String out;
  serializeJson(doc, out);
  server.send(doc["ok"] ? 200 : 502, "application/json", out);
}

void setupServer() {
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/sensors", HTTP_GET, handleSensors);
  server.on("/ai", HTTP_POST, handleAiForward);
  server.on("/ai/stream", HTTP_POST, handleAiStreamNow);
  server.onNotFound([]() {
    server.send(404, "application/json", "{\"error\":\"not_found\",\"routes\":[\"GET /status\",\"GET /sensors\",\"POST /ai\",\"POST /ai/stream\"]}");
  });
  server.begin();
  Serial.println("HTTP server started on port 80");
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\nESP32 sensor hub booting");

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
  state.oled_ok = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  if (!state.oled_ok) {
    Serial.printf("OLED init failed at address 0x%02X\n", OLED_ADDR);
  } else {
    drawStatus("Booting...");
  }

  dht.begin();
  scanWifiNetworks();
  connectWifi();
  setupServer();
  readSensors();
  postSensors();
  postLocalLanguage();
  drawStatus();
  // First automatic AI call happens after one normal loop interval so boot remains debuggable.
  state.last_ai_ms = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  server.handleClient();

  unsigned long now = millis();
  if (now - state.last_read_ms >= SENSOR_READ_MS) {
    readSensors();
    drawStatus();
  }
  if (now - state.last_post_ms >= POST_MS) {
    state.last_post_ms = now;
    postSensors();
    postLocalLanguage();
    drawStatus();
  }
  periodicAiIfDue();
  delay(10);
}
