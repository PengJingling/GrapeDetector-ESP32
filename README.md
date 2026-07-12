# GrapeDetector-ESP32

ESP32-S3 + OV camera + AS7341 support firmware and PC-side tools for:

```text
基于 YOLO 与多光谱融合的葡萄品质及农残风险智能检测系统
```

The ESP32-S3 captures grape images and exposes HTTP endpoints. The PC runs YOLO/Roboflow inference and later fuses visual results with AS7341 spectrum data.

## Current Architecture

```text
OV camera / AS7341
        |
     ESP32-S3
        |
  WiFi AP: GrapeDetector-ESP32
        |
      PC server
        |
YOLO / Roboflow / dashboard
```

## Hardware Notes

Tested board:

```text
ESP32-S3 N16R8
```

Temporary DuPont camera wiring for the current LXB-OVX640 style adapter:

| Camera adapter pin | ESP32-S3 GPIO / power |
| --- | --- |
| 3V3 | 3V3 |
| GND | GND |
| SDA | GPIO1 |
| SCL | GPIO2 |
| SYNC / VSYNC | GPIO4 |
| HERF / HREF | GPIO5 |
| PCLK | GPIO6 |
| D0 | GPIO8 |
| D1 | GPIO9 |
| D2 | GPIO10 |
| D3 | GPIO11 |
| D4 | GPIO12 |
| D5 | GPIO13 |
| D6 | GPIO14 |
| D7 | GPIO15 |
| RES | 3V3 |
| PWDN | GND |
| FLASH | GPIO40 |

Important:

- Leave GPIO46 unconnected during DuPont-wire testing.
- This adapter has no external XCLK pin, so firmware uses `CAM_PIN_XCLK = -1`.
- This adapter has no ESP32-controlled reset pin, so firmware uses `CAM_PIN_RESET = -1`.
- High-resolution still capture works best with short, clean wiring or the final PCB/FPC connection.

## AS7341

By default, AS7341 direct reading is disabled:

```cpp
#define AS7341_DIRECT_TO_ESP32 0
```

If AS7341 is wired directly to ESP32:

| AS7341 pin | ESP32-S3 |
| --- | --- |
| VIN/VCC | 3V3 |
| GND | GND |
| SDA | GPIO19 |
| SCL | GPIO41 |

Then set:

```cpp
#define AS7341_DIRECT_TO_ESP32 1
```

## PlatformIO

Open this folder in VS Code:

```text
C:\Users\pavan\Documents\物联网\GrapeQualityDetector
```

Compile:

```powershell
pio run
```

Upload:

```powershell
pio run -t upload
```

Serial monitor:

```powershell
pio device monitor -b 115200
```

## ESP32 Web API

Default AP:

```text
SSID: GrapeDetector-ESP32
Password: 12345678
URL: http://192.168.4.1
```

Useful endpoints:

| URL | Function |
| --- | --- |
| `/live` | Browser live monitor |
| `/capture.jpg` | QVGA still |
| `/capture-vga.jpg` | VGA still |
| `/capture-svga.jpg` | SVGA still |
| `/capture-xga.jpg` | XGA still, recommended for YOLO |
| `/capture-sxga.jpg` | SXGA still test |
| `/capture-uxga.jpg` | UXGA still test |
| `/health` | Device status |
| `/settings.json` | Camera settings |
| `/flash?on=1` | Turn camera FLASH on |
| `/flash?on=0` | Turn camera FLASH off |
| `/exposure?mode=low` | Lower manual exposure |
| `/exposure?mode=auto` | Auto exposure |
| `/spectrum.json` | AS7341 data if direct mode is enabled |
| `/stm32.json` | Latest STM32 UART line |

MJPEG stream:

```text
http://192.168.4.1:81/stream
```

## PC Tools

Install Python dependencies:

```powershell
python -m pip install ultralytics opencv-python
```

Local camera dashboard:

```powershell
python pc_server\dashboard.py
```

Open:

```text
http://127.0.0.1:8765
```

YOLO dashboard with a local model:

```powershell
python pc_server\yolo_dashboard.py --model models\grape_yolo.pt --image-endpoint capture-xga.jpg
```

Roboflow hosted grape model dashboard:

```powershell
python pc_server\roboflow_grape_dashboard.py --api-key YOUR_ROBOFLOW_KEY --image-endpoint capture-xga.jpg
```

Open:

```text
http://127.0.0.1:8767
```

## YOLO Classes

Recommended final classes:

```text
ripe_grape
unripe_grape
bad_grape
```

Public Roboflow grape models may only detect an entire grape bunch or generic `grape`. For per-berry counting and bad fruit localization, train or fine-tune a grape-berry model with per-grape labels.

Capture training images:

```powershell
python pc_server\capture_yolo_images.py --split train --count 80 --image-endpoint capture-xga.jpg
python pc_server\capture_yolo_images.py --split val --count 20 --image-endpoint capture-xga.jpg
```

Train:

```powershell
python pc_server\train_grape_yolo.py --data datasets\grape.yaml --epochs 50 --imgsz 960 --batch 4
```

Copy the trained `best.pt` to:

```text
models\grape_yolo.pt
```
