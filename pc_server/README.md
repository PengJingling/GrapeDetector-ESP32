# PC server tools

These scripts run on the computer while it is connected to the ESP32 hotspot.

ESP32 hotspot:

```text
SSID: GrapeDetector-ESP32
Password: 12345678
Device URL: http://192.168.4.1
```

## Collect samples

Save one image and metadata:

```powershell
python pc_server\collect_samples.py --count 1 --label grape_test
```

Save ten images:

```powershell
python pc_server\collect_samples.py --count 10 --interval 2 --label grape_test
```

Data is saved to:

```text
data\samples
```

Each sample contains:

```text
capture.jpg
metadata.json
```

## Local dashboard

Run:

```powershell
python pc_server\dashboard.py
```

Open:

```text
http://127.0.0.1:8765
```

The dashboard shows the latest ESP32 image, `/health`, and `/stm32.json`.
