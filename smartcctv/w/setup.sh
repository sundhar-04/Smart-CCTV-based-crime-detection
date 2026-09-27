#!/usr/bin/env bash
set -e
pip install opencv-python-headless numpy scipy flask "supervision==0.30.4" ultralytics boxmot
mkdir -p models data out
B=https://github.com/AlexeyAB/darknet
curl -L -o models/yolov4-tiny.weights $B/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights
curl -L -o models/yolov4-tiny.cfg https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg
curl -L -o models/coco.names https://raw.githubusercontent.com/AlexeyAB/darknet/master/data/coco.names
curl -L -o data/vtest.avi https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/vtest.avi
