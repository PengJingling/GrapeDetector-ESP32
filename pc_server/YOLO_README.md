# YOLO integration

ESP32 only captures images. YOLO runs on the computer.

## Install

```powershell
python -m pip install ultralytics
```

## Model file

Put your trained grape model here:

```text
models\grape_yolo.pt
```

Recommended classes:

```text
normal_grape
rotten_grape
damaged_grape
```

The dashboard filters detections to grape-only classes by default. Generic COCO
labels such as `person` and `donut` are ignored and are not drawn.

## Browser dashboard

Connect the computer to `GrapeDetector-ESP32`, then run:

```powershell
cd C:\Users\pavan\Documents\物联网\GrapeQualityDetector
python pc_server\yolo_dashboard.py --model models\grape_yolo.pt
```

Open:

```text
http://127.0.0.1:8766
```

## Run once

```powershell
python pc_server\yolo_detect.py --model models\grape_yolo.pt
```

By default, YOLO reads `/capture.jpg`, matching the QVGA live stream more closely.
For a larger still image, use:

```powershell
python pc_server\yolo_dashboard.py --model models\grape_yolo.pt --image-endpoint capture-vga.jpg
```

Recommended for this project:

```powershell
python pc_server\yolo_dashboard.py --model models\grape_yolo.pt --image-endpoint capture-xga.jpg
```

## Capture images for labeling

```powershell
python pc_server\capture_yolo_images.py --split train --count 80 --image-endpoint capture-xga.jpg
python pc_server\capture_yolo_images.py --split val --count 20 --image-endpoint capture-xga.jpg
```

Label the images in YOLO format with these classes:

```text
0 normal_grape
1 rotten_grape
2 damaged_grape
```

Label files should be placed in:

```text
datasets\grape\labels\train
datasets\grape\labels\val
```

## Train grape model

```powershell
python pc_server\train_grape_yolo.py --data datasets\grape.yaml --epochs 80 --imgsz 960 --batch 4
```

After training, copy the best model to:

```text
models\grape_yolo.pt
```

Outputs:

```text
data\yolo\latest.jpg
data\yolo\latest_detected.jpg
data\yolo\latest_result.json
```

## Loop mode

```powershell
python pc_server\yolo_detect.py --model models\grape_yolo.pt --loop --interval 2
```

## Generic smoke test

This does not detect grapes well, but it verifies that YOLO can run:

```powershell
python pc_server\yolo_detect.py --model yolov8n.pt
python pc_server\yolo_dashboard.py --model yolov8n.pt
```

## Try a public Roboflow grape model

This uses a hosted Roboflow model named `grape-detection-oquct/14`.
It detects grapes only; it does not classify rotten or damaged grapes.

Get a Roboflow API key from your Roboflow account, then run:

```powershell
python pc_server\roboflow_grape_dashboard.py --api-key YOUR_ROBOFLOW_KEY --image-endpoint capture-xga.jpg
```

Open:

```text
http://127.0.0.1:8767
```

You can also set the key once:

```powershell
$env:ROBOFLOW_API_KEY="YOUR_ROBOFLOW_KEY"
python pc_server\roboflow_grape_dashboard.py --image-endpoint capture-xga.jpg
```
