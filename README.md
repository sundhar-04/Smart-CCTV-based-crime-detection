# 🛡️ Smart CCTV Based Crime Detection & Surveillance Platform

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-EE4C2C.svg)](https://pytorch.org/)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-00FFFF.svg)](https://docs.ultralytics.com/)
[![React](https://img.shields.io/badge/React-18.3+-61DAFB.svg)](https://reactjs.org/)
[![Vite](https://img.shields.io/badge/Vite-5.4+-646CFF.svg)](https://vitejs.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5+-3178C6.svg)](https://www.typescript.org/)

An end-to-end, enterprise-grade AI surveillance and crime detection system powering real-time security analytics. Combining **YOLOv8 deep learning**, a **motion-gated cascade**, a **multi-signal risk accumulation engine**, **tamper monitoring**, **cryptographically chained evidence logs (SHA-256)**, and an interactive **React Command Center UI**.

---

## 📸 Key Features

- **🎯 AI-Powered Multi-Model Threat Detection**:
  - **YOLOv8 Object Detection**: Detects persons, weapons, abandoned items, and suspicious movement. Uses a two-stage cascade with motion gating and crop verification to minimize GPU compute while preserving high detection accuracy.
  - **🤸 YOLOv8-Pose Violence & Fight Classifier**: Real-time 17-keypoint skeleton analysis detecting physical strikes/punches (wrist velocity spikes), overhead weapon swings, sudden sprint rushes, and collapsed/fallen subjects.
  - **🔪 Dedicated Weapon Detection**: Specialized classifier for firearms, edged weapons, and blunt objects.

- **📈 Risk Accumulation & Dynamic Alert Engine**:
  - Replaces binary detection noise with continuous risk scoring ($0 - 100$).
  - Accumulates threat scores based on restricted zone intrusions, loitering dwell time, velocity spikes, violent posture indicators, and night/after-hours temporal modifiers.
  - Includes alert budgeting to prevent notification fatigue.

- **⛓️ Cryptographic Chain of Custody (SHA-256)**:
  - Every detected incident generates an immutable SHA-256 hash block.
  - Linked hash chains ensure audit integrity and prevent unauthorized evidence manipulation or video deletion.

- **🎥 Live Camera Stream Manager & Ingestion**:
  - Seamless ingestion of RTSP streams, IP phone cameras, USB webcams, and pre-recorded footage.
  - Dynamic camera addition and configuration directly from the UI without restarting services.

- **🔗 Unified Cross-Camera ReID & Topology**:
  - Re-identification (ReID) framework mapping entity handoffs across unmonitored camera blind spots.
  - Visual Identity Topology graph showing real-time path trajectories and camera handoffs.

- **🗺️ Interactive GIS & Spatial Camera Map**:
  - Visual floorplan/map view displaying live camera statuses, field-of-view coverage cones, and real-time incident risk heat map.

- **🚨 Operator Dispatch & Alerting**:
  - Human-in-the-loop incident response: REVIEWING $\rightarrow$ CONFIRMED / DISMISSED.
  - Real-time Telegram Bot & HTTP Webhook integrations for instant mobile alerting upon confirmation.


---

## 🏗️ System Architecture

```text
                     ┌──────────────────────────────────────────────┐
                     │          React + TypeScript Frontend         │
                     │  (Command Center, Maps, Topology, Analysis)  │
                     └──────────────────────┬───────────────────────┘
                                            │ HTTP / REST & WebSockets
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │            FastAPI Backend Server            │
                     │   (Routers, CameraManager, CrossCamCoord)    │
                     └───────┬──────────────────────────────┬───────┘
                             │                              │
                             ▼                              ▼
             ┌────────────────────────────────┐  ┌───────────────────────┐
             │   AI Analytics & Vision Core   │  │  SQLite + SHA-256     │
             │   - YOLOv8 (Objects & Weapons) │  │  Cryptographic        │
             │   - YOLOv8-Pose (Strikes/Falls)│  │  Audit Chain          │
             │   - ByteTrack & Cross-Cam ReID │  └───────────────────────┘
             │   - Multi-Signal Risk Engine   │
             └────────────────────────────────┘
```

---

## 📁 Repository Structure

```text
├── backend/                       # FastAPI Backend API Server
│   ├── main.py                    # Application entry point & router mounting
│   ├── bridge.py                  # Bridge connecting FastAPI to SmartCCTV engine
│   ├── camera_manager.py          # Multi-camera live stream ingestion & frame buffer
│   ├── cross_cam_coordinator.py   # Cross-camera ReID and identity handoff engine
│   ├── database.py                # SQLite database schema & connection manager
│   ├── models.py                  # Pydantic data schemas
│   ├── ws.py                      # WebSocket broadcast manager
│   └── routers/                   # API Endpoints (alerts, cameras, analysis, topology...)
│
├── web/                           # Modern React + Vite + TypeScript Web Interface
│   ├── src/
│   │   ├── pages/                 # CommandCenter, IdentityTopology, CameraMap, VideoAnalysis...
│   │   ├── components/            # AddCameraModal, ChartCanvas, RiskBadge, ZoneEditor...
│   │   ├── api/                   # Axios REST API client bindings
│   │   └── ws/                    # Real-time WebSocket connection hooks
│   ├── package.json               # Node dependencies & npm scripts
│   └── vite.config.ts             # Vite build & dev server config
│
├── smartcctv/                     # Core Computer Vision & AI Analytics Engine
│   └── w/
│       ├── smartcctv/
│       │   ├── detector_yolo8.py  # YOLOv8 object detector with crop verification
│       │   ├── pose_violence.py   # YOLOv8-pose keypoint strike & fight detection
│       │   ├── weapon_detector.py # Weapon detection pipeline
│       │   ├── tracker.py         # Multi-target tracker & trajectory estimation
│       │   ├── risk.py            # Multi-signal risk accumulation engine
│       │   ├── evidence.py        # Video evidence recorder & SHA-256 hash chain
│       │   ├── tamper.py          # Camera tamper & occlusion monitor
│       │   └── run.py             # CLI runner for standalone processing
│       └── eval/                  # Evaluation suite & benchmark scripts
│
├── yolov8n.pt                     # Pre-trained YOLOv8 object weights
├── yolov8n-pose.pt                # Pre-trained YOLOv8 pose keypoint weights
├── requirements.txt               # Python dependencies
└── README.md                      # Project documentation & setup guide
```

---

## ⚙️ Setup & Installation Guide

### Prerequisites

Ensure you have the following software installed:
- **Python**: `3.9` or higher
- **Node.js**: `18.0` or higher
- **npm**: `9.0` or higher
- *(Optional)* **NVIDIA CUDA ToolKit**: For GPU-accelerated PyTorch detection.

---

### Step 1: Clone the Repository

```bash
git clone https://github.com/sundhar-04/Smart-CCTV-based-crime-detection.git
cd Smart-CCTV-based-crime-detection
```

---

### Step 2: Set Up Python Backend Environment

1. **Create a virtual environment**:
   ```bash
   # Windows (PowerShell / Command Prompt)
   python -m venv venv
   .\venv\Scripts\activate

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Python dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

### Step 3: Set Up Web Frontend Environment

1. **Navigate to the `web` directory**:
   ```bash
   cd web
   ```

2. **Install Node dependencies**:
   ```bash
   npm install
   ```

3. **Return to root directory**:
   ```bash
   cd ..
   ```

---

## 🚀 Running the Application

### 1. Launch the Backend API Server

Activate your Python virtual environment, then start the FastAPI server:

```bash
# From the project root directory:
python -m backend.main
```
*The FastAPI backend will start running at `http://localhost:8000` (API Docs at `http://localhost:8000/docs`).*

---

### 2. Launch the Web Frontend

In a separate terminal window, start the Vite development server:

```bash
cd web
npm run dev
```
*Open your browser and navigate to `http://localhost:5173` to access the Meridian Command Center UI.*

---

### 3. Run Standalone CLI Video Analysis Engine (Optional)

You can run the SmartCCTV core engine directly from the command line:

```bash
python -m smartcctv.w.smartcctv.run --config smartcctv/w/smartcctv/config.json
```

---

### 4. Run Test Suite

To verify system components, risk engines, and tamper detectors:

```bash
python smartcctv/w/smartcctv/tests/test_all.py
```

---

## 🔧 Configuration & Tuning

- **Risk Weights Configuration**: Located at `smartcctv/w/smartcctv/config.json`
  - Modify detection confidence thresholds (`thr`), loitering weight (`loiter`), zone intrusion multiplier (`restricted_zone`), and camera metadata.
- **Telegram & Webhook Notifications**:
  - Set environment variables to enable instant emergency dispatch:
    ```bash
    export TELEGRAM_TOKEN="your_bot_token"
    export TELEGRAM_CHAT_ID="your_chat_id"
    export WEBHOOK_URL="https://your-security-dispatch.com/api/alert"
    ```

---

## 📡 API Reference Overview

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `GET /api/cameras` | `GET` | Retrieve status, location, and parameters of all registered cameras |
| `POST /api/cameras` | `POST` | Register a new camera stream (RTSP, IP phone feed, webcam, video) |
| `DELETE /api/cameras/{id}` | `DELETE` | Deregister and remove a camera feed |
| `GET /api/cameras/{id}/snapshot` | `GET` | Retrieve the latest real-time frame snapshot from a live camera |
| `GET /api/topology` | `GET` | Query multi-camera network topology, blind-spot links, and handoff state |
| `POST /api/analysis/upload` | `POST` | Upload video file for automated YOLOv8 crime/risk analysis |
| `GET /api/analysis/jobs/{id}` | `GET` | Get real-time progress and results of a video analysis job |
| `GET /api/alerts` | `GET` | Query active and historical threat alerts |
| `POST /api/alerts/{id}/decision` | `POST` | Operator review decision (`CONFIRMED` / `DISMISSED`) |
| `GET /api/system/health` | `GET` | System hardware resource usage (CPU, RAM, GPU, VRAM) |
| `WS /ws` | `WebSocket` | Live telemetry, real-time alert pushes, and system status updates |

---

## 🤝 Contributing & License

Developed for AI-powered automated video surveillance, threat detection, and public safety operations.

Contributions are welcome! Please feel free to open Issues or Submit Pull Requests.

**Author**: [sundhar-04](https://github.com/sundhar-04)
