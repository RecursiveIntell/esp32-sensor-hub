# Architecture / Use Cases

This is a sensor node first, AI endpoint later.

## Current use cases

1. Read temperature/humidity locally.
2. Show readings and network status on a 1 inch OLED.
3. Connect to `purplemama` WiFi.
4. Push readings to a computer over HTTP.
5. Let the computer store, plot, forward, or trigger automation from those readings.
6. Expose simple HTTP endpoints on the ESP32 for local status checks.

## Later use cases

1. More sensors, swapped in over time:
   - light
   - air quality / VOC / CO2
   - soil moisture
   - motion
   - sound level
   - voltage/current
   - door/window reed switches
   - whatever else gets wired later

2. AI endpoint mode:
   - ESP32 keeps latest physical sensor context.
   - GTX 1070 machine performs inference.
   - ESP32 provides `/ai` as a physical-world endpoint.
   - Request includes prompt/request plus latest sensor readings.
   - GPU server returns response.
   - ESP32 optionally shows short status/result on OLED.

## Boundary

ESP32 responsibilities:

- read sensors
- display status
- maintain WiFi
- expose local REST endpoints
- send compact JSON to LAN services
- forward AI requests with sensor context

GTX 1070 computer responsibilities:

- inference
- long-term data storage
- dashboards
- model orchestration
- heavier analysis

## Data payload

Sensor post shape:

```json
{
  "device_id": "esp32-sensor-hub-01",
  "uptime_ms": 123456,
  "wifi_rssi": -54,
  "ip": "192.168.50.x",
  "temperature_c": 22.4,
  "humidity_pct": 45.9,
  "heat_index_c": 22.1,
  "status": "ok"
}
```

Future sensors should be added under a `sensors` object once there are several of them. The first version keeps top-level temp/humidity fields for easy curl/debug use.

## Expansion rule

Do not hard-code future sensor assumptions into the AI path. The AI request should carry the latest sensor JSON as context so the GPU-side code can decide what matters.
