# Online Dataset Pretraining

Goal classes:

```text
0 ripe_grape
1 unripe_grape
2 bad_grape
```

The first online dataset target is Roboflow Universe:

```text
workspace: fruits-ripeness
project: grape-unripe
version: 2
```

It is useful for `ripe_grape` and `unripe_grape` pretraining. It does not fully solve bad fruit detection, so later add your own bad grape images or another rotten/damaged grape dataset.

## Download

Set your Roboflow private API key:

```powershell
$env:ROBOFLOW_API_KEY="YOUR_PRIVATE_KEY"
```

Download and remap labels:

```powershell
python pc_server\download_roboflow_dataset.py --workspace fruits-ripeness --project grape-unripe --version 2
```

The script imports images and YOLO labels into:

```text
datasets\grape
```

## Train

Quick first test:

```powershell
python pc_server\train_grape_yolo.py --data datasets\grape.yaml --epochs 20 --imgsz 960 --batch 4
```

Better initial training:

```powershell
python pc_server\train_grape_yolo.py --data datasets\grape.yaml --epochs 50 --imgsz 960 --batch 4
```

After training, copy:

```text
runs\grape\grape_berry_yolov8n\weights\best.pt
```

to:

```text
models\grape_yolo.pt
```

Then run:

```powershell
python pc_server\yolo_dashboard.py --model models\grape_yolo.pt --image-endpoint capture-xga.jpg
```
