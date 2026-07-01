#pragma once

#define WIFI_SSID "PurpleMama"
#define WIFI_PASSWORD_PRIMARY "DaDDY)#)$!1"
#define WIFI_PASSWORD_SECONDARY "FuCKYOU)#)$!1"

#define HUB_POST_URL "http://192.168.50.181:8088/api/sensor"
#define OLLAMA_MODEL "gemma4:12b"
#define AI_INFER_URL "http://192.168.50.69:11434/api/chat"
#define AI_STREAM_URL "http://192.168.50.69:11434/api/chat"
#define LOCAL_LANGUAGE_URL "http://192.168.50.181:8088/api/local_language"
#ifdef RI_ESP32S3_BUILD
#define DEVICE_ID "esp32s3-sensor-hub-01"
#else
#define DEVICE_ID "esp32-sensor-hub-01"
#endif

#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_ADDR 0x3C
#define OLED_SDA_PIN 21
#ifdef RI_ESP32S3_BUILD
// ESP32-S3 WROOM N16R8/N8R8 boards often reserve GPIO8/9 for PSRAM.
// GPIO21 + GPIO47 are the known-safe I2C pins from prior hardware work.
#define OLED_SCL_PIN 47
#else
#define OLED_SCL_PIN 22
#endif

#define DHT_PIN 4
#define DHT_TYPE DHT11

#define SENSOR_READ_MS 5000
#define POST_MS 10000
#define AI_INTERVAL_MS 300000
#define AI_STREAM_MAX_MS 120000
#define AI_PROMPT "Do not just repeat the sensor numbers. Interpret the room comfort from the temp/humidity, say if it feels normal/humid/dry/hot/cool, and give one practical action if useful. One short OLED-friendly sentence."
