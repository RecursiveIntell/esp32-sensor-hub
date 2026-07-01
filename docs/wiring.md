# Wiring

Default ESP32 dev board wiring.

## DHT22 / DHT11 temp-humidity sensor

DHT sensor pins vary by module. Check labels on the board.

Typical 3-pin DHT module:

- VCC -> 3.3V
- GND -> GND
- DATA -> GPIO4

Typical bare 4-pin DHT22 package, front grille facing you:

- Pin 1 VCC -> 3.3V
- Pin 2 DATA -> GPIO4
- Pin 3 NC
- Pin 4 GND -> GND

Use a 4.7k-10k pullup from DATA to 3.3V if using a bare sensor without module pullup.

## 1 inch SSD1306 OLED, I2C

Typical I2C OLED pins:

- VCC -> 3.3V
- GND -> GND
- SCL -> GPIO22
- SDA -> GPIO21

Default I2C address: 0x3C.
Some modules use 0x3D; change `OLED_ADDR` in `include/config.h` if needed.

## ESP32-S3 warning

If this moves to ESP32-S3 WROOM-1 N16R8, avoid GPIO8 and GPIO9. They are used by octal PSRAM and I2C will silently fail there. Use known-safe pins exposed by the board, e.g. SDA GPIO21 and SCL GPIO47 if available.
