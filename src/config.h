#pragma once

/*
  Grape Quality Detector wiring for the PCB expansion-board version.

  OV2640:
    Use the PCB 24P FPC camera socket. Do not wire the OV2640 by hand.

  AS7341:
    In this PCB document, AS7341 is on the STM32 upper board:
      VIN -> +3V3, GND -> GND, SCL -> STM32 PB6, SDA -> STM32 PB7.

    That means ESP32 cannot directly read AS7341 unless:
      1. You wire AS7341 to ESP32 Expansion 8P GPIO19/GPIO41, or
      2. STM32 reads AS7341 and sends spectrum data to ESP32 by UART.

  Important:
    GPIO1/GPIO2 are used by OV2640 CAM_SIOD/CAM_SIOC in this PCB version.
    Do not put AS7341 on GPIO1/GPIO2.
*/

// Set to 1 only if AS7341 is directly wired to ESP32.
// If your PCB upper STM32 reads AS7341, keep this as 0 for now.
#define AS7341_DIRECT_TO_ESP32 0

// Optional direct AS7341 wiring through ESP32 lower-board Expansion 8P.
// Expansion 8P pin 3 = GPIO19, pin 4 = GPIO41.
#define AS7341_SDA_PIN 19
#define AS7341_SCL_PIN 41

// Optional fixed white LED control. Keep -1 if the white light is powered
// directly from USB/5V and is not controlled by ESP32.
#define WHITE_LED_PIN -1
#define WHITE_LED_ACTIVE_HIGH 1

// Camera adapter FLASH/LED control pin for temporary DuPont wiring.
// Wire camera board FLASH -> ESP32 GPIO40. Leave -1 if not connected.
#define CAMERA_FLASH_PIN 40
#define CAMERA_FLASH_ACTIVE_HIGH 1

// WiFi station mode. Leave empty to start a local AP named GrapeDetector.
#define WIFI_SSID ""
#define WIFI_PASSWORD ""

// Fallback AP settings when WIFI_SSID is empty or connection fails.
#define AP_SSID "GrapeDetector-ESP32"
#define AP_PASSWORD "12345678"

// PCB lower-board OV2640 24P FPC pin map from the wiring document.
// This LXB-OVX640 adapter exposes RES but not XCLK. It appears to have its
// own clock source on the camera adapter board, so ESP32 does not drive XCLK.
// Wire RES to 3V3 and PWDN to GND.
#define CAM_PIN_PWDN  -1
#define CAM_PIN_RESET -1
#define CAM_PIN_XCLK  -1
#define CAM_PIN_SIOD  1
#define CAM_PIN_SIOC  2

// Temporary DuPont-wire build:
// Avoid GPIO46 here because it is an ESP32-S3 strapping pin and can stop
// the board from booting when a hand-wired camera drives it during reset.
// Wire OV_D7 to GPIO15 instead.
#define CAM_PIN_D7    15
#define CAM_PIN_D6    14
#define CAM_PIN_D5    13
#define CAM_PIN_D4    12
#define CAM_PIN_D3    11
#define CAM_PIN_D2    10
#define CAM_PIN_D1    9
#define CAM_PIN_D0    8
#define CAM_PIN_VSYNC 4
#define CAM_PIN_HREF  5
#define CAM_PIN_PCLK  6

// Temporary DuPont wiring is much less stable than an FPC/PCB camera path.
// Use a lower XCLK and smaller frame first; raise them after capture works.
#define CAMERA_XCLK_FREQ_HZ 10000000
#define CAMERA_STREAM_FRAME_SIZE FRAMESIZE_QVGA
#define CAMERA_SNAPSHOT_FRAME_SIZE FRAMESIZE_VGA
#define CAMERA_SVGA_FRAME_SIZE FRAMESIZE_SVGA
#define CAMERA_XGA_FRAME_SIZE FRAMESIZE_XGA
#define CAMERA_SXGA_FRAME_SIZE FRAMESIZE_SXGA
#define CAMERA_HIGHRES_FRAME_SIZE FRAMESIZE_UXGA
#define CAMERA_JPEG_QUALITY 16
#define CAMERA_LIVE_REFRESH_MS 450
#define CAMERA_STREAM_PORT 81
#define CAMERA_STREAM_DELAY_MS 180
#define CAMERA_DEFAULT_BRIGHTNESS 1
#define CAMERA_DEFAULT_MANUAL_EXPOSURE 1
#define CAMERA_DEFAULT_AEC_VALUE 160
#define CAMERA_DEFAULT_AGC_GAIN 2

// ESP32 <-> STM32 board-to-board UART from the PCB document.
#define STM32_UART_TX_PIN 17
#define STM32_UART_RX_PIN 18
#define STM32_UART_BAUD 115200
